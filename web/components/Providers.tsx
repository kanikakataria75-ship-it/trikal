"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [qc] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          // every key carries as_of, so cached answers for a past date stay valid forever
          queries: { staleTime: 5 * 60_000, gcTime: 30 * 60_000, retry: 1, refetchOnWindowFocus: false },
        },
      }),
  );
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}
