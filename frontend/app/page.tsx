import { PatientResults } from "./patients/PatientResults";
import { DeviceDashboard } from "./DeviceDashboard";

export default function Home() {
  return process.env.NEXT_PUBLIC_APP_MODE === "public" ? <PatientResults /> : <DeviceDashboard />;
}
