import {useNavigate} from "react-router-dom";
import LessonWorkspace from "../../adaptive-learning-app/student-app/src/LessonWorkspace";
import {configureStudentTransport} from "../../adaptive-learning-app/student-app/src/api";
import {studentTransport} from "./self-directed-api";

configureStudentTransport(studentTransport);

export default function SDLWorkspace({assignmentId}) {
  const navigate=useNavigate();
  return <div className="platform-sdl"><LessonWorkspace assignmentId={assignmentId} onBack={()=>navigate("/student")} embedded/></div>;
}
