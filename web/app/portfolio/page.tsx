import Link from "next/link";
import { getPortfolio, getAnalyses, getChanges, getWatchlist, getHealthTrends } from "@/lib/api";
import type { Portfolio, Analysis, ChangeReport, WatchlistItem, HealthTrends } from "@/lib/types";
import PortfolioView from "./portfolio-view";

export const dynamic = "force-dynamic";

export default async function PortfolioPage() {
  let portfolio: Portfolio | null = null;
  let analyses: Analysis[] = [];
  let changes: ChangeReport[] = [];
  let watchlist: WatchlistItem[] = [];
  let healthTrends: HealthTrends = {};
  let error: string | null = null;
  try {
    [portfolio, analyses, changes, watchlist, healthTrends] = await Promise.all([
      getPortfolio(),
      getAnalyses(),
      getChanges(),
      getWatchlist(),
      getHealthTrends(),
    ]);
  } catch (e) {
    error = e instanceof Error ? e.message : String(e);
  }

  return (
    <main className="wrap">
      <div className="nav-row">
        <Link href="/" className="back">← กลับหน้ารวม</Link>
      </div>
      <header className="top">
        <h1>Portfolio</h1>
        <p>โพซิชันที่ถืออยู่จริง · กำไร/ขาดทุน + edge เทียบ benchmark · research, not advice</p>
      </header>

      {error || !portfolio ? (
        <div className="error">
          Cannot reach the API ({error ?? "no data"}). Start it with{" "}
          <code>uvicorn src.api.main:app --port 8000</code>
        </div>
      ) : (
        <PortfolioView
          portfolio={portfolio}
          analyses={analyses}
          changes={changes}
          watchlist={watchlist}
          healthTrends={healthTrends}
        />
      )}

      <p className="disclaimer">
        Educational research tool. Not investment advice — จำนวน/ราคาที่ถือเป็นข้อมูลที่คุณกรอกเอง.
      </p>
    </main>
  );
}