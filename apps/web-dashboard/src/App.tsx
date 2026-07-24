import { AlertTriangle, CheckCircle2, MailSearch, RefreshCw, Search, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { normalizeBehaviorLabel, riskCategoryFromScore, riskCategoryLabel, type DetectedBehavior, type EmailScanRecord, type RiskCategory } from "@phishing-defense/shared";
import { getEmailScan, getEmailScans } from "./api";

type RiskGroup = RiskCategory;

export function scanRisk(scan: EmailScanRecord): RiskGroup {
  return riskCategoryFromScore(scan.emailRiskScore);
}

export function App() {
  const [scans, setScans] = useState<EmailScanRecord[]>([]);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | RiskGroup>("all");
  const [selected, setSelected] = useState<EmailScanRecord | null>(null);
  const [detailError, setDetailError] = useState("");
  const load = useCallback(async () => { setState("loading"); try { const records = await getEmailScans(); setScans(records.sort((a, b) => Date.parse(b.scannedAt) - Date.parse(a.scannedAt))); setState("ready"); } catch { setState("error"); } }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { const id = new URLSearchParams(window.location.search).get("scanId"); if (!id) return; setDetailError(""); void getEmailScan(id).then(setSelected).catch(error => setDetailError(error instanceof Error ? error.message : "The scan could not be loaded.")); }, []);

  const counts = useMemo(() => scans.reduce((acc, scan) => { acc[scanRisk(scan)] += 1; return acc; }, { high: 0, suspicious: 0, low: 0 }), [scans]);
  const behaviorCounts = useMemo(() => {
    const map = new Map<string, number>(); scans.flatMap(scan => scan.detectedBehaviors).forEach(item => { const label = normalizeBehaviorLabel(item.type); if (label) map.set(label, (map.get(label) ?? 0) + 1); });
    return [...map.entries()].sort((a, b) => b[1] - a[1]);
  }, [scans]);
  const visible = useMemo(() => scans.filter(scan => {
    const text = `${scan.subject} ${scan.senderName} ${scan.senderEmail}`.toLowerCase();
    return text.includes(query.trim().toLowerCase()) && (filter === "all" || scanRisk(scan) === filter);
  }), [scans, query, filter]);

  return <main>
    <header><div className="brand"><ShieldAlert size={24}/> Sentinel</div><span className="prototype">Rule-based prototype</span></header>
    <section className="hero"><div><p className="eyebrow">SECURITY ANALYSIS</p><h1>Email Security Analysis</h1><p>Behavioral and technical analysis of scanned email messages</p></div><button onClick={() => void load()} disabled={state === "loading"}><RefreshCw size={16}/> Refresh</button></section>
    <section className="metrics" aria-label="Scan summary">
      <Metric icon={<MailSearch/>} label="Emails Scanned" value={scans.length}/><Metric icon={<ShieldAlert/>} label="High-Risk Emails" value={counts.high} tone="high"/><Metric icon={<AlertTriangle/>} label="Suspicious Emails" value={counts.suspicious} tone="suspicious"/><Metric icon={<CheckCircle2/>} label="Low-Risk Emails" value={counts.low} tone="low"/>
    </section>
    {state === "loading" && <section className="panel state" role="status"><span className="spinner"/>Loading security analyses…</section>}
    {state === "error" && <section className="panel state error" role="alert"><h2>Couldn’t load scan records</h2><p>Verify that the analysis backend is running, then try again.</p><button onClick={() => void load()}>Try again</button></section>}
    {state === "ready" && scans.length === 0 && <section className="panel state"><MailSearch size={36}/><h2>No email scans yet</h2><p>Scan an opened Gmail message to populate security analytics.</p></section>}
    {state === "ready" && scans.length > 0 && <>
      <section className="analysis-grid">
        <RiskDistribution counts={counts} total={scans.length}/>
        <BehaviorRanking values={behaviorCounts}/>
      </section>
      <section className="panel info-card"><h2>Behavioral Representation Layer</h2><p>The Behavioral Representation Layer converts social-engineering tactics found in the message into structured indicators. These behavioral indicators may be combined with conventional email and URL features to support the final classification and explanation.</p></section>
      <section className="panel recent"><div className="panel-title"><div><h2>Recent scans</h2><p>Newest completed analyses appear first.</p></div><div className="controls"><label className="search"><Search size={15}/><span className="sr-only">Search scans</span><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search subject or sender"/></label><label><span className="sr-only">Filter risk level</span><select value={filter} onChange={event => setFilter(event.target.value as typeof filter)}><option value="all">All risk levels</option><option value="high">High Risk</option><option value="suspicious">Suspicious</option><option value="low">Low Risk</option></select></label></div></div>
        {visible.length === 0 ? <div className="filtered-empty">No scans match the current search and filter.</div> : <ScanTable scans={visible} onSelect={setSelected}/>} 
      </section>
    </>}
    {selected && <ScanDetails scan={selected} onClose={() => setSelected(null)}/>} 
    {detailError && <div className="modal-backdrop"><section className="details detail-error" role="alert"><h2>Full analysis unavailable</h2><p>{detailError}</p><button onClick={() => setDetailError("")}>Close</button></section></div>}
  </main>;
}

function Metric({ icon, label, value, tone = "neutral" }: { icon: React.ReactNode; label: string; value: number; tone?: string }) { return <article className={`metric ${tone}`}><div className="icon">{icon}</div><div><p>{label}</p><strong>{value}</strong></div></article>; }

function RiskDistribution({ counts, total }: { counts: Record<RiskGroup, number>; total: number }) {
  const high = counts.high / total * 100, suspicious = counts.suspicious / total * 100;
  return <section className="panel chart-panel"><div className="panel-title"><h2>Risk distribution</h2><p>Classification across stored scans</p></div><div className="risk-chart"><div className="donut" role="img" aria-label={`${counts.high} high risk, ${counts.suspicious} suspicious, ${counts.low} low risk`} style={{ background: `conic-gradient(#b42318 0 ${high}%,#a15c00 ${high}% ${high + suspicious}%,#14745b ${high + suspicious}% 100%)` }}><span>{total}<small>scans</small></span></div><ul className="legend"><li><i className="dot high"/>High Risk <strong>{counts.high}</strong></li><li><i className="dot suspicious"/>Suspicious <strong>{counts.suspicious}</strong></li><li><i className="dot low"/>Low Risk <strong>{counts.low}</strong></li></ul></div></section>;
}

function BehaviorRanking({ values }: { values: [string, number][] }) {
  const max = values[0]?.[1] ?? 1;
  return <section className="panel chart-panel"><div className="panel-title"><h2>Most detected behaviors</h2><p>Behavioral Representation Layer indicators</p></div>{values.length === 0 ? <p className="chart-empty">No recognized behavioral indicators detected.</p> : <ol className="bars">{values.map(([label, count]) => <li key={label}><span>{label}</span><div><i style={{ width: `${count / max * 100}%` }}/></div><strong>{count}</strong></li>)}</ol>}</section>;
}

function ScanTable({ scans, onSelect }: { scans: EmailScanRecord[]; onSelect: (scan: EmailScanRecord) => void }) {
  return <div className="scan-list"><table><thead><tr><th>Subject</th><th>Sender</th><th>Risk</th><th>Score</th><th>Strongest behaviors</th><th>Scanned</th><th><span className="sr-only">Action</span></th></tr></thead><tbody>{scans.map(scan => <tr key={scan.scanId}><td data-label="Subject"><strong>{scan.subject}</strong></td><td data-label="Sender"><strong>{scan.senderName}</strong><small>{scan.senderEmail}</small></td><td data-label="Risk"><RiskBadge risk={scanRisk(scan)}/></td><td data-label="Score">{scan.emailRiskScore}/100</td><td data-label="Behaviors">{behaviorSummary(scan.detectedBehaviors)}</td><td data-label="Scanned">{formatDate(scan.scannedAt)}</td><td><button className="text-button" onClick={() => onSelect(scan)}>View details</button></td></tr>)}</tbody></table></div>;
}

function ScanDetails({ scan, onClose }: { scan: EmailScanRecord; onClose: () => void }) {
  const behavioral = scan.detectedBehaviors.filter(item => normalizeBehaviorLabel(item.type));
  return <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}><section className="details" role="dialog" aria-modal="true" aria-labelledby="details-title"><div className="details-head"><div><p className="eyebrow">SCAN DETAILS</p><h2 id="details-title">{scan.subject}</h2></div><button onClick={onClose} aria-label="Close scan details">×</button></div>
    <DetailSection title="Email Information"><Definition label="Sender" value={`${scan.senderName} <${scan.senderEmail}>`}/><Definition label="Scan timestamp" value={formatDate(scan.scannedAt)}/><Definition label="Final classification" value={<RiskBadge risk={scanRisk(scan)}/>}/></DetailSection>
    <DetailSection title="Risk Assessment"><Definition label="Risk score" value={`${scan.emailRiskScore}/100`}/>{scan.phishingProbability !== null && <Definition label="Phishing probability" value={`${Math.round(scan.phishingProbability * 100)}%`}/>}<Definition label="Score source" value={scan.scoreSource}/>{scan.modelVersion && <Definition label="Model version" value={scan.modelVersion}/>}</DetailSection>
    <DetailSection title="Behavioral Analysis" subtitle="Behavioral Representation Layer">{behavioral.length ? behavioral.map(item => <Indicator key={`${item.type}-${item.evidence}`} item={item}/>) : <p>No recognized behavioral indicators were returned.</p>}</DetailSection>
    <DetailSection title="Technical Analysis"><Definition label="URLs found" value={String(scan.urlCount)}/><Definition label="Sender domain" value={scan.senderDomain}/>{scan.technicalIndicators.length ? scan.technicalIndicators.map(item => <article className="indicator" key={`${item.type}-${item.evidence}`}><strong>{item.type.replaceAll("_", " ")}</strong><p>Evidence: “{item.evidence}”</p></article>) : <p>No technical mismatches were returned.</p>}</DetailSection>
    <DetailSection title="Recommendation" subtitle="Human-centered guidance"><p>{scan.recommendation}</p></DetailSection>
    <DetailSection title="User Interaction"><ul className="interaction-list"><li className={scan.emailOpened ? "done" : ""}>Email opened</li><li className="done">Email scanned</li><li className={scan.userReported ? "done" : ""}>User reported the email</li><li className={scan.viewFullAnalysisSelected ? "done" : ""}>View Full Analysis selected</li></ul></DetailSection>
  </section></div>;
}

function DetailSection({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) { return <section className="detail-section"><div><h3>{title}</h3>{subtitle && <small>{subtitle}</small>}</div>{children}</section>; }
function Definition({ label, value }: { label: string; value: React.ReactNode }) { return <div className="definition"><span>{label}</span><strong>{value}</strong></div>; }
function Indicator({ item }: { item: DetectedBehavior }) { const label = normalizeBehaviorLabel(item.type) ?? item.type.replaceAll("_", " "); return <article className="indicator"><div><strong>{label}</strong><span>{Math.round(item.confidence * 100)}% indicator strength</span></div><p>Evidence: “{item.evidence}”</p><small>{interpretation(label)}</small></article>; }
function RiskBadge({ risk }: { risk: RiskGroup }) { return <span className={`badge ${risk}`}>{riskCategoryLabel(risk)}</span>; }
function behaviorSummary(items: DetectedBehavior[]) { const labels = items.map(item => normalizeBehaviorLabel(item.type)).filter((value): value is string => Boolean(value)).slice(0, 3); return labels.length ? labels.join(", ") : "None detected"; }
function interpretation(label: string) { const map: Record<string, string> = { Urgency: "Pressures the recipient to act quickly.", Authority: "Invokes a position of power or expertise.", Fear: "Uses a threat or negative consequence to influence action.", "Credential Request": "Encourages disclosure or entry of account credentials.", Impersonation: "Presents the sender as another person or organization.", Reward: "Offers a benefit to motivate engagement.", Scarcity: "Frames an opportunity as limited." }; return map[label] ?? "Contributes to the structured behavioral assessment."; }
function formatDate(value: string) { return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
