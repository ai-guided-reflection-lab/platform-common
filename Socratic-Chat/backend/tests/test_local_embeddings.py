from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError
from PyPDF2 import PdfWriter
from PyPDF2.generic import DecodedStreamObject, DictionaryObject, NameObject

from app import rag, settings


def local_client(monkeypatch, dimensions=4):
    monkeypatch.setattr(settings, 'EMBEDDING_PROVIDER', 'ollama')
    monkeypatch.setattr(settings, 'EMBEDDING_MODEL', 'qwen3-embedding:0.6b')
    monkeypatch.setattr(settings, 'EMBEDDING_DIMENSIONS', dimensions)
    monkeypatch.setattr(settings, 'EMBEDDING_BATCH_SIZE', 2)
    monkeypatch.setattr(settings, 'OPENAI_API_KEY', '')
    client = MagicMock()
    def embed(**kwargs):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1]*dimensions) for _ in kwargs['input']])
    client.embeddings.create.side_effect=embed
    return client


def test_local_qwen_batches_and_uses_no_openai_key(monkeypatch):
    client = local_client(monkeypatch)
    with patch('openai.OpenAI') as factory:
        factory.return_value.__enter__.return_value=client
        vectors=rag.create_embeddings(['one','two','three'])
    assert len(vectors)==3 and all(len(v)==4 for v in vectors)
    assert factory.call_args.kwargs['base_url']==settings.OLLAMA_API_BASE_URL
    assert factory.call_args.kwargs['api_key']=='ollama'
    assert [c.kwargs['input'] for c in client.embeddings.create.call_args_list]==[['one','two'],['three']]
    assert client.embeddings.create.call_args.kwargs['model']=='qwen3-embedding:0.6b'


@pytest.mark.parametrize('vectors', [[[0.1]*3], []])
def test_invalid_embedding_output_is_rejected_before_storing(monkeypatch,vectors):
    client=local_client(monkeypatch)
    client.embeddings.create.side_effect=None
    client.embeddings.create.return_value=SimpleNamespace(data=[SimpleNamespace(embedding=v) for v in vectors])
    with patch('openai.OpenAI') as factory:
        factory.return_value.__enter__.return_value=client
        with pytest.raises(rag.EmbeddingError):rag.create_embeddings(['document'])


def test_unavailable_local_model_returns_actionable_error(monkeypatch):
    client=local_client(monkeypatch)
    client.embeddings.create.side_effect=APIConnectionError(request=httpx.Request('POST','http://127.0.0.1:11434/v1/embeddings'))
    with patch('openai.OpenAI') as factory:
        factory.return_value.__enter__.return_value=client
        with pytest.raises(rag.EmbeddingError,match='Ollama embedding model qwen3-embedding'):
            rag.create_embeddings(['document'])


def test_small_pdf_with_readable_text_creates_a_chunk(tmp_path,monkeypatch):
    writer=PdfWriter()
    writer.add_blank_page(width=200,height=200)
    page=writer.pages[0]
    font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
    page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
    stream=DecodedStreamObject(); stream.set_data(b'BT /F1 12 Tf 10 100 Td (Databases store related records in tables.) Tj ET')
    page[NameObject('/Contents')]=writer._add_object(stream)
    pdf=tmp_path/'small.pdf'
    with pdf.open('wb') as output:writer.write(output)
    assert pdf.stat().st_size<2000
    monkeypatch.setattr(rag,'create_embeddings',lambda texts:[[0.1]*1024 for _ in texts])
    with patch.object(rag.db,'replace_document_chunks',return_value=1) as store:
        _,count=rag.ingest_pdf_file(pdf,course_id='course',file_id='file')
    assert count==1
    assert 'Databases store related records' in store.call_args.args[3][0]['text']


def test_scanned_pdf_does_not_report_success_with_zero_chunks(tmp_path,monkeypatch):
    monkeypatch.setattr(rag,'read_pdf_pages',lambda _:[(1,'')])
    with patch.object(rag.db,'replace_document_chunks') as store:
        with pytest.raises(rag.DocumentTextError,match='no extractable text'):
            rag.ingest_pdf_file(tmp_path/'scan.pdf',file_id='file')
    store.assert_not_called()


def test_snapshot_never_compares_vectors_from_different_models(monkeypatch):
    monkeypatch.setattr(settings,'EMBEDDING_MODEL','qwen3-embedding:0.6b')
    monkeypatch.setattr(rag,'create_embeddings',lambda _:[[1.,0.]])
    sources=rag.retrieve_snapshot('database', [{
        'document_id':'doc','chunk_id':'chunk','title':'Database',
        'text':'A database stores records.', 'embedding':[1.,0.], 'embedding_model':'old-model',
    }])
    assert sources and sources[0].dense_similarity==0
    assert sources[0].sparse_score>0
