import { Link } from "react-router-dom";

export default function SelfDirectedInstructorHome() {
  return <>
    <Link className="back" to="/professor">← All tools</Link>
    <div className="page-heading"><div>
      <p className="context">Self-Directed Learning</p>
      <h1>Build an adaptive learning experience.</h1>
      <p>Use the SDL instructor app to prepare course materials, review the lesson, and publish it to your students.</p>
    </div></div>
    <section className="panel">
      <h2>One lesson, one connected student workspace</h2>
      <p>The SDL instructor app manages lessons, recipients, publication, and learning evidence. Connect it to the same SDL backend and database used by this platform.</p>
      <p>Assign lessons to the email address students use to sign in here. Their published lessons appear under Self-Directed Learning and open in the SDL student workspace.</p>
      <p>Start the instructor app using the SDL launcher. Its local address is printed when it starts.</p>
    </section>
  </>;
}
