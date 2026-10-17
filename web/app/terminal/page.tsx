import { Suspense } from "react";
import Terminal from "@/components/terminal/Terminal";

export const metadata = { title: "TRIKAL — Terminal" };

export default function Page() {
  return (
    <Suspense>
      <Terminal />
    </Suspense>
  );
}
