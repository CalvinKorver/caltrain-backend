import { useState } from "react";

const LAYERS = {
  ingestion: {
    title: "Data Ingestion",
    color: "#E8F5E9",
    border: "#2E7D32",
    accent: "#1B5E20",
    sources: [
      {
        name: "511 GTFS-RT",
        icon: "🚂",
        status: "free",
        detail: "Official Caltrain service alerts, trip updates, and vehicle positions via 511.org API. Free with API key. 60 req/hr rate limit.",
        endpoint: "api.511.org/transit/servicealerts",
        polling: "Every 30s",
        priority: "Primary",
        setup: "Sign up at 511.org/open-data → get API key → poll GTFS-RT protobuf feed"
      },
      {
        name: "Reddit",
        icon: "📱",
        status: "free",
        detail: "Monitor r/caltrain and r/bayarea for delay reports, track incidents, and crowd-sourced ETAs. Free tier (100 QPM) for personal/non-commercial use.",
        endpoint: "oauth.reddit.com/r/caltrain/new",
        polling: "Every 2 min",
        priority: "High",
        setup: "Create Reddit app (script type) → OAuth2 auth → poll /new and /hot endpoints"
      },
      {
        name: "Caltrain.com Scraper",
        icon: "🌐",
        status: "free",
        detail: "Scrape the official service advisories page as a fallback. Simple HTML parsing for banner alerts and service advisory text.",
        endpoint: "caltrain.com/alerts",
        polling: "Every 5 min",
        priority: "Secondary",
        setup: "BeautifulSoup or Playwright scraper → parse alert banners → extract severity + text"
      },
      {
        name: "Google Maps Platform",
        icon: "🗺️",
        status: "free",
        detail: "Google Routes API transit directions to detect when Caltrain ETAs spike vs. schedule. Compare expected vs. actual travel times to infer delays. $200/mo free credit covers this.",
        endpoint: "routes.googleapis.com/transit",
        polling: "Every 5 min",
        priority: "Signal boost",
        setup: "Google Cloud project → enable Routes API → compare transit ETA deltas over time"
      }
    ]
  },
  intelligence: {
    title: "Intelligence Layer",
    color: "#E3F2FD",
    border: "#1565C0",
    accent: "#0D47A1",
    components: [
      {
        name: "Severity Classifier",
        icon: "🧠",
        detail: "Claude API call to classify incoming reports into severity levels: CRITICAL (service suspended, major delays 30+ min), WARNING (15–30 min delays, single train), INFO (minor delays, schedule changes). Uses structured output for consistent scoring.",
        tech: "Claude Haiku (fast + cheap)"
      },
      {
        name: "Deduplicator",
        icon: "🔗",
        detail: "Cross-references reports from different sources about the same incident. Uses fuzzy matching on location, time window (±10 min), and incident keywords. Merges into a single unified incident with confidence score.",
        tech: "Embedding similarity + time window"
      },
      {
        name: "Ground Truth Engine",
        icon: "📊",
        detail: "Compares official Caltrain reported delays vs. Reddit crowd-sourced reports vs. actual GTFS-RT trip updates. Learns which sources are most accurate over time. Catches cases like today: 15 min official → 60 min actual.",
        tech: "PostgreSQL + historical tracking"
      }
    ]
  },
  notification: {
    title: "Notification & Delivery",
    color: "#FFF3E0",
    border: "#E65100",
    accent: "#BF360C",
    channels: [
      {
        name: "SMS (Twilio)",
        icon: "💬",
        detail: "Push SMS alerts for CRITICAL severity. Users subscribe with phone number + route preferences. ~$0.0079/msg. Estimated cost: <$5/mo for personal use.",
        cost: "~$0.01/msg"
      },
      {
        name: "Web Dashboard",
        icon: "🖥️",
        detail: "Real-time status page showing current Caltrain conditions, source reliability scores, and incident timeline. Shareable URL for other commuters.",
        cost: "Free (hosting)"
      },
    ]
  }
};

const TECH_STACK = {
  backend: [
    { name: "Python + FastAPI", why: "Async polling, easy protobuf parsing, great Reddit/HTTP libs" },
    { name: "Celery + Redis", why: "Scheduled polling tasks, rate limit management, caching" },
    { name: "PostgreSQL", why: "Incident storage, user preferences, historical accuracy tracking" },
  ],
  infra: [
    { name: "Railway or Fly.io", why: "Cheap hosting (~$5-10/mo), easy deploy, always-on workers" },
    { name: "Upstash Redis", why: "Free tier for caching + Celery broker" },
    { name: "Supabase", why: "Free PostgreSQL + auth for user subscriptions" },
  ],
  apis: [
    { name: "511.org GTFS-RT", why: "Free, official, real-time Caltrain data" },
    { name: "Reddit Data API", why: "Free tier, 100 QPM, OAuth2" },
    { name: "Google Routes API", why: "Transit ETA delta detection, $200/mo free credit" },
    { name: "Claude Haiku API", why: "Fast severity classification (~$0.25/1M tokens)" },
    { name: "Twilio", why: "SMS delivery, pay-per-message" },
  ]
};

const PHASES = [
  {
    phase: "1",
    title: "MVP — Personal Alerts",
    duration: "1–2 weekends",
    items: [
      "511 GTFS-RT service alerts polling",
      "Reddit r/caltrain monitoring",
      "Claude severity classification",
      "SMS alerts to your phone via Twilio",
    ]
  },
  {
    phase: "2",
    title: "Dashboard + Dedup",
    duration: "2–3 weekends",
    items: [
      "Web dashboard with real-time status",
      "Cross-source deduplication",
      "Google Maps ETA delta detection",
      "Historical accuracy tracking",
      "Route-specific filtering (your commute)",
    ]
  },
  {
    phase: "3",
    title: "Community Launch",
    duration: "3–4 weekends",
    items: [
      "User registration + route preferences",
      "Push notifications (web + mobile)",
      "Slack/Discord bot integration",
      "Public status page for sharing",
    ]
  }
];

const COST_ESTIMATE = [
  { item: "511.org API", cost: "Free", note: "API key required" },
  { item: "Reddit API", cost: "Free", note: "Non-commercial, 100 QPM" },
  { item: "Google Maps Platform", cost: "Free", note: "$200/mo credit covers it" },
  { item: "Claude Haiku API", cost: "~$1–3/mo", note: "Light classification volume" },
  { item: "Twilio SMS", cost: "~$2–5/mo", note: "Personal use alerts" },
  { item: "Railway hosting", cost: "~$5–10/mo", note: "Worker + web server" },
  { item: "Supabase (DB)", cost: "Free", note: "Free tier sufficient" },
  { item: "Upstash Redis", cost: "Free", note: "Free tier sufficient" },
];

const mono = "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace";
const sans = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif";

export default function CaltrainAlertArch() {
  const [activeTab, setActiveTab] = useState("architecture");
  const [expandedCard, setExpandedCard] = useState(null);

  const tabs = [
    { id: "architecture", label: "Architecture" },
    { id: "stack", label: "Tech Stack" },
    { id: "phases", label: "Roadmap" },
    { id: "costs", label: "Costs" },
  ];

  return (
    <div style={{
      fontFamily: sans,
      background: "#0F1117",
      color: "#E4E4E7",
      minHeight: "100vh",
      padding: "24px",
    }}>
      <div style={{ marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
          <span style={{ fontSize: 28 }}>🚨</span>
          <h1 style={{
            fontSize: 24,
            fontWeight: 700,
            color: "#FAFAFA",
            margin: 0,
            fontFamily: mono,
            letterSpacing: "-0.5px"
          }}>
            caltrain-alerts
          </h1>
          <span style={{
            background: "#22C55E20",
            color: "#22C55E",
            padding: "3px 10px",
            borderRadius: 6,
            fontSize: 11,
            fontWeight: 600,
            fontFamily: mono,
          }}>
            v0.1 spec
          </span>
        </div>
        <p style={{
          color: "#71717A",
          fontSize: 14,
          margin: 0,
          lineHeight: 1.5,
        }}>
          Crowd-sourced transit delay detection — because the official "15 min delay" was actually 60 minutes
        </p>
      </div>

      <div style={{
        display: "flex",
        gap: 4,
        marginBottom: 24,
        background: "#1A1B23",
        padding: 4,
        borderRadius: 10,
        width: "fit-content",
      }}>
        {tabs.map(t => (
          <button
            key={t.id}
            onClick={() => { setActiveTab(t.id); setExpandedCard(null); }}
            style={{
              padding: "8px 16px",
              borderRadius: 8,
              border: "none",
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 600,
              fontFamily: sans,
              background: activeTab === t.id ? "#27272A" : "transparent",
              color: activeTab === t.id ? "#FAFAFA" : "#71717A",
              transition: "all 0.15s ease",
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "architecture" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {Object.entries(LAYERS).map(([key, layer]) => (
            <div key={key}>
              <div style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
                marginBottom: 12,
              }}>
                <div style={{
                  width: 4,
                  height: 20,
                  background: layer.border,
                  borderRadius: 2,
                }} />
                <h2 style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: "#FAFAFA",
                  margin: 0,
                  fontFamily: mono,
                }}>
                  {layer.title}
                </h2>
              </div>

              <div style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                gap: 12,
              }}>
                {(layer.sources || layer.components || layer.channels || []).map((item, i) => {
                  const cardId = `${key}-${i}`;
                  const isExpanded = expandedCard === cardId;
                  return (
                    <div
                      key={i}
                      onClick={() => setExpandedCard(isExpanded ? null : cardId)}
                      style={{
                        background: "#1A1B23",
                        border: `1px solid ${isExpanded ? layer.border : "#27272A"}`,
                        borderRadius: 12,
                        padding: 16,
                        cursor: "pointer",
                        transition: "all 0.2s ease",
                      }}
                    >
                      <div style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        marginBottom: 8,
                      }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <span style={{ fontSize: 20 }}>{item.icon}</span>
                          <span style={{
                            fontSize: 14,
                            fontWeight: 700,
                            color: "#FAFAFA",
                          }}>
                            {item.name}
                          </span>
                        </div>
                        {item.status && (
                          <span style={{
                            background: item.status === "free" ? "#22C55E15" : "#F59E0B15",
                            color: item.status === "free" ? "#22C55E" : "#F59E0B",
                            padding: "2px 8px",
                            borderRadius: 4,
                            fontSize: 10,
                            fontWeight: 700,
                            fontFamily: mono,
                            letterSpacing: "0.5px",
                          }}>
                            {item.status.toUpperCase()}
                          </span>
                        )}
                        {item.cost && (
                          <span style={{
                            color: "#71717A",
                            fontSize: 11,
                            fontFamily: mono,
                          }}>
                            {item.cost}
                          </span>
                        )}
                        {item.tech && (
                          <span style={{
                            color: "#71717A",
                            fontSize: 11,
                            fontFamily: mono,
                          }}>
                            {item.tech}
                          </span>
                        )}
                      </div>

                      {item.polling && (
                        <div style={{
                          display: "flex",
                          gap: 12,
                          marginBottom: 8,
                        }}>
                          <span style={{
                            fontSize: 11,
                            color: "#71717A",
                            fontFamily: mono,
                          }}>
                            ⏱ {item.polling}
                          </span>
                          <span style={{
                            fontSize: 11,
                            color: "#71717A",
                            fontFamily: mono,
                          }}>
                            📌 {item.priority}
                          </span>
                        </div>
                      )}

                      <p style={{
                        fontSize: 12,
                        color: "#A1A1AA",
                        lineHeight: 1.6,
                        margin: 0,
                      }}>
                        {item.detail}
                      </p>

                      {isExpanded && item.endpoint && (
                        <div style={{
                          marginTop: 12,
                          padding: 10,
                          background: "#0F1117",
                          borderRadius: 8,
                          fontFamily: mono,
                          fontSize: 11,
                          color: "#22C55E",
                          lineHeight: 1.8,
                        }}>
                          <div><span style={{ color: "#71717A" }}>endpoint:</span> {item.endpoint}</div>
                          {item.setup && (
                            <div style={{ marginTop: 6, color: "#A1A1AA" }}>
                              <span style={{ color: "#71717A" }}>setup:</span>{" "}
                              {item.setup.split("\n").map((line, j) => (
                                <div key={j}>{line}</div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {key !== "notification" && (
                <div style={{
                  display: "flex",
                  justifyContent: "center",
                  padding: "12px 0 0",
                }}>
                  <div style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 2,
                  }}>
                    <div style={{ width: 2, height: 16, background: "#27272A" }} />
                    <span style={{ color: "#3F3F46", fontSize: 16 }}>▼</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {activeTab === "stack" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          {Object.entries(TECH_STACK).map(([category, items]) => (
            <div key={category}>
              <h3 style={{
                fontSize: 13,
                fontWeight: 700,
                color: "#71717A",
                textTransform: "uppercase",
                letterSpacing: "1px",
                fontFamily: mono,
                marginBottom: 12,
              }}>
                {category}
              </h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {items.map((item, i) => (
                  <div key={i} style={{
                    background: "#1A1B23",
                    border: "1px solid #27272A",
                    borderRadius: 10,
                    padding: "12px 16px",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    gap: 16,
                    flexWrap: "wrap",
                  }}>
                    <span style={{
                      fontWeight: 700,
                      fontSize: 14,
                      color: "#FAFAFA",
                      fontFamily: mono,
                    }}>
                      {item.name}
                    </span>
                    <span style={{
                      fontSize: 12,
                      color: "#A1A1AA",
                      textAlign: "right",
                    }}>
                      {item.why}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === "phases" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          {PHASES.map((phase) => (
            <div key={phase.phase} style={{
              background: "#1A1B23",
              border: "1px solid #27272A",
              borderRadius: 12,
              padding: 20,
              position: "relative",
            }}>
              <div style={{
                position: "absolute",
                top: -1,
                left: 20,
                right: 20,
                height: 3,
                background: phase.phase === "1" ? "#22C55E" : phase.phase === "2" ? "#3B82F6" : "#A855F7",
                borderRadius: "0 0 4px 4px",
              }} />
              <div style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: 14,
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{
                    background: phase.phase === "1" ? "#22C55E20" : phase.phase === "2" ? "#3B82F620" : "#A855F720",
                    color: phase.phase === "1" ? "#22C55E" : phase.phase === "2" ? "#3B82F6" : "#A855F7",
                    width: 28,
                    height: 28,
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 13,
                    fontWeight: 800,
                    fontFamily: mono,
                  }}>
                    {phase.phase}
                  </span>
                  <h3 style={{ fontSize: 16, fontWeight: 700, color: "#FAFAFA", margin: 0 }}>
                    {phase.title}
                  </h3>
                </div>
                <span style={{
                  fontSize: 12,
                  color: "#71717A",
                  fontFamily: mono,
                }}>
                  {phase.duration}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {phase.items.map((item, i) => (
                  <div key={i} style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    padding: "4px 0",
                  }}>
                    <div style={{
                      width: 6,
                      height: 6,
                      borderRadius: "50%",
                      background: "#3F3F46",
                      flexShrink: 0,
                    }} />
                    <span style={{ fontSize: 13, color: "#A1A1AA" }}>{item}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === "costs" && (
        <div>
          <div style={{
            background: "#1A1B23",
            border: "1px solid #27272A",
            borderRadius: 12,
            overflow: "hidden",
          }}>
            <div style={{
              display: "grid",
              gridTemplateColumns: "1fr 100px 1fr",
              padding: "12px 16px",
              background: "#0F1117",
              borderBottom: "1px solid #27272A",
              fontFamily: mono,
              fontSize: 11,
              fontWeight: 700,
              color: "#71717A",
              textTransform: "uppercase",
              letterSpacing: "0.5px",
            }}>
              <span>Service</span>
              <span>Cost</span>
              <span>Note</span>
            </div>
            {COST_ESTIMATE.map((row, i) => (
              <div key={i} style={{
                display: "grid",
                gridTemplateColumns: "1fr 100px 1fr",
                padding: "12px 16px",
                borderBottom: i < COST_ESTIMATE.length - 1 ? "1px solid #1E1E26" : "none",
                fontSize: 13,
              }}>
                <span style={{ color: "#FAFAFA", fontWeight: 600 }}>{row.item}</span>
                <span style={{
                  color: row.cost === "Free" ? "#22C55E" : "#F59E0B",
                  fontFamily: mono,
                  fontWeight: 700,
                  fontSize: 12,
                }}>
                  {row.cost}
                </span>
                <span style={{ color: "#71717A", fontSize: 12 }}>{row.note}</span>
              </div>
            ))}
            <div style={{
              display: "grid",
              gridTemplateColumns: "1fr 100px 1fr",
              padding: "14px 16px",
              background: "#0F1117",
              borderTop: "1px solid #27272A",
              fontWeight: 800,
            }}>
              <span style={{ color: "#FAFAFA", fontFamily: mono }}>TOTAL (estimated)</span>
              <span style={{ color: "#22C55E", fontFamily: mono, fontSize: 14 }}>~$8–18/mo</span>
              <span style={{ color: "#71717A", fontSize: 12 }}>Phase 1 personal use</span>
            </div>
          </div>

          <div style={{
            marginTop: 20,
            padding: 16,
            background: "#22C55E08",
            border: "1px solid #22C55E20",
            borderRadius: 10,
            fontSize: 13,
            color: "#A1A1AA",
            lineHeight: 1.6,
          }}>
            <span style={{ fontWeight: 700, color: "#22C55E" }}>Key insight: </span>
            By skipping X/Twitter (which requires $200/mo minimum for search access), the entire stack
            runs on essentially free-tier services plus a few dollars for Twilio SMS and hosting.
            Reddit fills the crowd-sourced gap — and based on your experience today, Reddit was already
            the more reliable source for real delay info anyway.
          </div>
        </div>
      )}
    </div>
  );
}
