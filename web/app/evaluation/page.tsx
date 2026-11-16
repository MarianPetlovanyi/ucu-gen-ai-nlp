import type { Metadata } from "next";
import EvaluationDashboard from "@/components/evaluation";

export const metadata: Metadata = { title: "Evaluation · NDA Playbook Reviewer" };

export default function Page() {
  return <EvaluationDashboard />;
}
