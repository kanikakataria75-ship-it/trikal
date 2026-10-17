import { Suspense } from "react";
import Compare from "@/components/compare/Compare";

export const metadata = { title: "TRIKAL — Compare" };

export default function Page() {
  return (
    <Suspense>
      <Compare />
    </Suspense>
  );
}
