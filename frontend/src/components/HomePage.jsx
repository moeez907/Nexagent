import React, { useState } from 'react';
import {
  Sparkles,
  ArrowRight,
  Play,
  Cpu,
  Globe,
  ShieldCheck,
  Zap,
  Terminal,
  Copy,
  Check,
  Search,
  TrendingUp,
  Compass,
  Newspaper,
  Layers,
  Monitor,
  Eye,
  Lock,
  ExternalLink,
  ChevronRight,
  Activity,
  Bot
} from 'lucide-react';

export default function HomePage({ onGetStarted, onSignIn, onSelectMission, user }) {
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState('json');
  const [ctaEmail, setCtaEmail] = useState('');

  const sampleJson = `{
  "status": "COMPLETED",
  "query": "Samsung 990 PRO 4TB NVMe SSD",
  "vendor": "Verified Retailer",
  "live_price": "$319.99",
  "in_stock": true,
  "rating": 4.8,
  "reviews_count": 1248,
  "specs": {
    "form_factor": "M.2 2280",
    "interface": "PCIe Gen 4.0 x4",
    "read_speed": "7,450 MB/s",
    "write_speed": "6,900 MB/s"
  },
  "actions_taken": 6,
  "dom_nodes_evaluated": 1420,
  "execution_time_ms": 418
}`;

  const copyToClipboard = () => {
    navigator.clipboard?.writeText(sampleJson);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleCtaSubmit = (e) => {
    e.preventDefault();
    onGetStarted(ctaEmail);
  };

  const scrollToSection = (e, targetId) => {
    if (e && e.preventDefault) e.preventDefault();
    const element = document.getElementById(targetId);
    if (element) {
      const navOffset = 76;
      const elementPosition = element.getBoundingClientRect().top;
      const offsetPosition = elementPosition + window.pageYOffset - navOffset;

      window.scrollTo({
        top: offsetPosition,
        behavior: 'smooth'
      });
    }
  };

  return (
    <div className="home-page-container">
      {/* Top Header / Navigation */}
      <header className="home-nav">
        <div className="home-nav-inner">
          <div className="home-brand" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
            <img src="/logo.png" alt="Nexagent" className="home-brand-img" />
            <span className="home-brand-text">
              Nex<span className="gradient-text">agent</span>
            </span>
          </div>

          <nav className="home-nav-links">
            <a href="#features" onClick={(e) => scrollToSection(e, 'features')}>Features</a>
            <a href="#how-it-works" onClick={(e) => scrollToSection(e, 'how-it-works')}>How it Works</a>
            <a href="#missions" onClick={(e) => scrollToSection(e, 'missions')}>Agent Missions</a>
            <a href="#architecture" onClick={(e) => scrollToSection(e, 'architecture')}>Architecture</a>
            <a href="#features" onClick={(e) => scrollToSection(e, 'features')}>Docs</a>
          </nav>

          <div className="home-nav-actions">
            {user ? (
              <button className="home-btn-workspace" onClick={() => onGetStarted()}>
                Open Workspace <ArrowRight size={15} />
              </button>
            ) : (
              <>
                <button className="home-btn-signin" onClick={onSignIn}>
                  Sign In
                </button>
                <button className="home-btn-get-started" onClick={() => onGetStarted()}>
                  Get Started
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="home-hero-section">
        <div className="home-hero-content">
          {/* Release Pill Badge */}
          <div className="home-hero-pill" onClick={() => onGetStarted()}>
            <span className="pill-dot">✦</span>
            <span className="pill-title">NEXAGENT 2.0 RELEASE</span>
            <span className="pill-sep">/</span>
            <span className="pill-desc">Real-Time Vision &amp; DOM Synthesis</span>
            <ArrowRight size={13} className="pill-arrow" />
          </div>

          {/* Main Hero Headline */}
          <h1 className="home-hero-title">
            AI Agents That<br />
            <span className="gradient-text-hero">Browse, Understand,</span> and Act.
          </h1>

          {/* Hero Subtitle - Real Web Agent capability */}
          <p className="home-hero-subtitle">
            Dispatch autonomous AI browser agents to navigate complex web portals,
            overcome dynamic bot challenges, dissect live DOM trees, and return clean
            structured intelligence in real time.
          </p>

          {/* CTA Group */}
          <div className="home-hero-cta-group">
            <button className="btn-primary-glow" onClick={() => onGetStarted()}>
              Get Started <ArrowRight size={17} />
            </button>
            <a
              href="#interactive-demo"
              className="btn-secondary-glass"
              onClick={(e) => scrollToSection(e, 'interactive-demo')}
            >
              <Play size={15} className="play-icon" /> Watch Live Demo
            </a>
          </div>
        </div>

        {/* Hero Interactive Browser Mockup Window */}
        <div id="interactive-demo" className="hero-browser-mockup">
          {/* Window Chrome Header */}
          <div className="mockup-window-header">
            <div className="mockup-traffic-lights">
              <span className="light light-red" />
              <span className="light light-yellow" />
              <span className="light light-green" />
            </div>

            <div className="mockup-objective-bar">
              <span className="objective-label">CURRENT OBJECTIVE</span>
              <span className="objective-text">"Search Samsung 990 PRO on Amazon, filter rating &gt; 4.5, extract lowest unit price with spec breakdown"</span>
            </div>

            <div style={{ width: 80 }} />
          </div>

          {/* Address & Control Toolbar */}
          <div className="mockup-toolbar">
            <div className="mockup-url-bar">
              <Lock size={12} className="url-lock" />
              <span className="url-text">https://www.amazon.com/s?k=samsung+990+pro+4tb</span>
              <span className="url-meta">Headless Chromium 124.0.0 (Stealth Mode)</span>
            </div>
            <div className="mockup-toolbar-actions">
              <span className="toolbar-tag">Real-Time Vision Active</span>
            </div>
          </div>

          {/* Split Body: Live Simulated Viewport on Left, Live Terminal/JSON on Right */}
          <div className="mockup-split-body">
            {/* Left: Simulated Web Viewport with Agent Action Highlight */}
            <div className="mockup-viewport-pane">
              <div className="mockup-page-content">
                {/* Simulated Target Webpage elements */}
                <div className="web-page-banner">
                  <div className="web-search-sim">
                    <Search size={13} color="#94a3b8" />
                    <span>samsung 990 pro 4tb nvme</span>
                  </div>
                  <div className="web-badge-prime">Prime Deals</div>
                </div>

                <div className="web-product-card-active">
                  <div className="web-product-thumb">
                    <div className="thumb-box">SSD</div>
                  </div>
                  <div className="web-product-info">
                    <div className="web-product-title">
                      Samsung 990 PRO PCIe 4.0 NVMe SSD 4TB
                    </div>
                    <div className="web-product-seller">
                      Official Flagship Store • 4.8 Stars (1,248 Reviews) • 7000+ sold last month
                    </div>
                    <div className="web-product-tags">
                      <span className="web-tag free-ship">FREE SHIPPING</span>
                      <span className="web-tag stock">IN STOCK • 4TB NVMe</span>
                    </div>
                  </div>
                  <div className="web-product-pricing">
                    <div className="web-price">$319.99</div>
                    <div className="web-list-price">List: $359.99</div>
                  </div>

                  {/* Visual Agent Target Indicator */}
                  <div className="agent-cursor-target">
                    <div className="target-bounding-box" />
                    <div className="target-tooltip">
                      <span className="target-pulse" />
                      Agent Action: [Click & Inspect DOM: #specs-table]
                    </div>
                  </div>
                </div>

                {/* Second result row */}
                <div className="web-product-card-secondary">
                  <div className="web-product-thumb secondary-thumb">
                    <div className="thumb-box">SSD</div>
                  </div>
                  <div className="web-product-info">
                    <div className="web-product-title">
                      Crucial T700 4TB Gen5 NVMe M.2
                    </div>
                    <div className="web-product-seller">
                      Crucial Store • 4.7 Stars (873 Reviews)
                    </div>
                  </div>
                  <div className="web-product-pricing">
                    <div className="web-price">$379.99</div>
                  </div>
                </div>
              </div>

              {/* Bottom Agent Decision Overlay Banner */}
              <div className="agent-action-overlay-bar">
                <div className="overlay-indicator">
                  <span className="overlay-dot" />
                  <strong>Autonomous Decision:</strong> Dynamic element mutation resolved. Auto-injected resilient selector in 48ms.
                </div>
                <div className="overlay-step">Step 4/6</div>
              </div>
            </div>

            {/* Right: Live Agent Terminal & Structured Data Stream */}
            <div className="mockup-terminal-pane">
              <div className="terminal-header">
                <div className="terminal-title">
                  <Terminal size={14} color="#38bdf8" />
                  <span>LIVE DATA STREAM</span>
                </div>
                <div className="terminal-tabs">
                  <button
                    className={`terminal-tab ${activeTab === 'json' ? 'active' : ''}`}
                    onClick={() => setActiveTab('json')}
                  >
                    JSON
                  </button>
                  <button
                    className={`terminal-tab ${activeTab === 'dom' ? 'active' : ''}`}
                    onClick={() => setActiveTab('dom')}
                  >
                    DOM TREE
                  </button>
                  <button
                    className={`terminal-tab ${activeTab === 'actions' ? 'active' : ''}`}
                    onClick={() => setActiveTab('actions')}
                  >
                    LOGS
                  </button>
                </div>
              </div>

              <div className="terminal-code-body">
                {activeTab === 'json' && (
                  <pre className="code-block">
                    <code>
                      <span className="c-brace">&#123;</span>{'\n'}
                      {'  '}<span className="c-key">"status"</span>: <span className="c-str">"COMPLETED"</span>,{'\n'}
                      {'  '}<span className="c-key">"query"</span>: <span className="c-str">"Samsung 990 PRO 4TB NVMe SSD"</span>,{'\n'}
                      {'  '}<span className="c-key">"vendor"</span>: <span className="c-str">"Verified Retailer"</span>,{'\n'}
                      {'  '}<span className="c-key">"live_price"</span>: <span className="c-val-price">"$319.99"</span>,{'\n'}
                      {'  '}<span className="c-key">"in_stock"</span>: <span className="c-bool">true</span>,{'\n'}
                      {'  '}<span className="c-key">"rating"</span>: <span className="c-num">4.8</span>,{'\n'}
                      {'  '}<span className="c-key">"reviews_count"</span>: <span className="c-num">1248</span>,{'\n'}
                      {'  '}<span className="c-key">"specs"</span>: <span className="c-brace">&#123;</span>{'\n'}
                      {'    '}<span className="c-key">"form_factor"</span>: <span className="c-str">"M.2 2280"</span>,{'\n'}
                      {'    '}<span className="c-key">"interface"</span>: <span className="c-str">"PCIe Gen 4.0 x4"</span>,{'\n'}
                      {'    '}<span className="c-key">"read_speed"</span>: <span className="c-str">"7,450 MB/s"</span>,{'\n'}
                      {'    '}<span className="c-key">"write_speed"</span>: <span className="c-str">"6,900 MB/s"</span>{'\n'}
                      {'  '}<span className="c-brace">&#125;</span>,{'\n'}
                      {'  '}<span className="c-key">"actions_taken"</span>: <span className="c-num">6</span>,{'\n'}
                      {'  '}<span className="c-key">"dom_nodes_evaluated"</span>: <span className="c-num">1420</span>,{'\n'}
                      {'  '}<span className="c-key">"execution_time_ms"</span>: <span className="c-num">418</span>{'\n'}
                      <span className="c-brace">&#125;</span>
                    </code>
                  </pre>
                )}

                {activeTab === 'dom' && (
                  <pre className="code-block dom-code">
                    <code>
                      <span className="c-comment">&lt;!-- Cleaned Semantic Accessibility Tree --&gt;</span>{'\n'}
                      <span className="c-tag">&lt;div</span> <span className="c-attr">role</span>=<span className="c-str">"main"</span> <span className="c-attr">id</span>=<span className="c-str">"search-results"</span><span className="c-tag">&gt;</span>{'\n'}
                      {'  '}<span className="c-tag">&lt;article</span> <span className="c-attr">data-asin</span>=<span className="c-str">"B0CHGT1KFQ"</span><span className="c-tag">&gt;</span>{'\n'}
                      {'    '}<span className="c-tag">&lt;h2&gt;</span>Samsung 990 PRO 4TB<span className="c-tag">&lt;/h2&gt;</span>{'\n'}
                      {'    '}<span className="c-tag">&lt;span</span> <span className="c-attr">class</span>=<span className="c-str">"a-price-whole"</span><span className="c-tag">&gt;</span>319<span className="c-tag">&lt;/span&gt;</span>{'\n'}
                      {'    '}<span className="c-tag">&lt;button</span> <span className="c-attr">id</span>=<span className="c-str">"specs-btn"</span> <span className="c-attr">aria-expanded</span>=<span className="c-str">"true"</span><span className="c-tag">&gt;</span>{'\n'}
                      {'      '}Specifications Table &gt;&gt;{'\n'}
                      {'    '}<span className="c-tag">&lt;/button&gt;</span>{'\n'}
                      {'  '}<span className="c-tag">&lt;/article&gt;</span>{'\n'}
                      <span className="c-tag">&lt;/div&gt;</span>
                    </code>
                  </pre>
                )}

                {activeTab === 'actions' && (
                  <div className="terminal-logs">
                    <div className="log-line"><span className="log-time">00:00.024</span> <span className="log-info">[INIT]</span> Spawning isolated Chromium context with stealth fingerprint</div>
                    <div className="log-line"><span className="log-time">00:00.112</span> <span className="log-nav">[NAVIGATE]</span> Target URL loaded (HTTP 200 OK)</div>
                    <div className="log-line"><span className="log-time">00:00.204</span> <span className="log-dom">[DOM_PARSE]</span> Pruned 3,840 raw nodes to 42 interactive semantic nodes</div>
                    <div className="log-line"><span className="log-time">00:00.288</span> <span className="log-action">[ACTION]</span> Dispatched simulated natural click to target #specs-table</div>
                    <div className="log-line"><span className="log-time">00:00.370</span> <span className="log-extract">[EXTRACT]</span> Schema parsed with 100% confidence rating</div>
                    <div className="log-line success"><span className="log-time">00:00.418</span> <span className="log-ok">[DONE]</span> Mission accomplished successfully</div>
                  </div>
                )}
              </div>

              <div className="terminal-footer">
                <span className="terminal-footer-label">Target: //table[@id='specs'] -&gt; Extracted</span>
                <button className="copy-btn" onClick={copyToClipboard}>
                  {copied ? <Check size={12} color="#10b981" /> : <Copy size={12} />}
                  <span>{copied ? 'Copied' : 'Copy Payload'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Enterprise Tech Bar */}
      <section id="architecture" className="tech-proof-bar">
        <div className="tech-proof-inner">
          <span className="tech-proof-label">BUILT FOR ENTERPRISE-GRADE WEB INTELLIGENCE</span>
          <div className="tech-proof-badges">
            <div className="proof-badge">
              <Cpu size={16} className="badge-ico" />
              <span>NVIDIA Nemotron 3.5 LLM</span>
            </div>
            <div className="proof-badge">
              <Globe size={16} className="badge-ico" />
              <span>Chromium Stealth Engine</span>
            </div>
            <div className="proof-badge">
              <Zap size={16} className="badge-ico" />
              <span>Real-Time WebSocket Stream</span>
            </div>
            <div className="proof-badge">
              <ShieldCheck size={16} className="badge-ico" />
              <span>Anti-Fingerprint & CAPTCHA Protocol</span>
            </div>
          </div>
        </div>
      </section>

      {/* Feature Section: UNRIVALED AUTONOMY */}
      <section id="features" className="home-section-features">
        <div className="section-header">
          <div className="section-pill">UNRIVALED AUTONOMY</div>
          <h2 className="section-title">Architected for Sites That Defeat Simple Scrapers</h2>
          <p className="section-subtitle">
            Traditional headless scripts break when pages mutate. Nexagent uses visual-language
            reasoning and DOM perception to navigate web pages just like a human operator.
          </p>
        </div>

        <div className="features-grid">
          {/* Card 1 */}
          <div className="feature-card">
            <div className="feature-icon-wrapper icon-blue">
              <Compass size={22} color="#2563eb" />
            </div>
            <h3 className="feature-title">Autonomous Multi-Step Navigation</h3>
            <p className="feature-desc">
              Handles interactive forms, multi-tier pagination, drop-down combo selectors,
              and multi-domain navigation paths with self-correcting dynamic retries.
            </p>
            <a href="#how-it-works" className="feature-link">
              Adaptive Policies &amp; Resumes <ChevronRight size={14} />
            </a>
          </div>

          {/* Card 2 */}
          <div className="feature-card">
            <div className="feature-icon-wrapper icon-emerald">
              <Eye size={22} color="#059669" />
            </div>
            <h3 className="feature-title">Real-Time DOM Perception</h3>
            <p className="feature-desc">
              Synthesizes raw DOM trees into semantic nodes. Cleans dynamic noise, extracts specific
              nested visual pricing, and guarantees type-safe JSON or CSV output.
            </p>
            <a href="#how-it-works" className="feature-link">
              Semantic Self-Correction <ChevronRight size={14} />
            </a>
          </div>

          {/* Card 3 */}
          <div className="feature-card">
            <div className="feature-icon-wrapper icon-violet">
              <Monitor size={22} color="#7c3aed" />
            </div>
            <h3 className="feature-title">Side-by-Side Live Viewport</h3>
            <p className="feature-desc">
              Watch live remote browser video frames at 30 FPS. Seamlessly intervene with low-latency
              keyboard and mouse override for 2FA or physical verification flows.
            </p>
            <a href="#interactive-demo" className="feature-link">
              Human-in-the-Loop Mode <ChevronRight size={14} />
            </a>
          </div>
        </div>
      </section>

      {/* Execution Pipeline Section */}
      <section id="how-it-works" className="home-section-pipeline">
        <div className="section-header">
          <div className="section-pill">EXECUTION PIPELINE</div>
          <h2 className="section-title">From Natural Language to Verified Intel in Three Steps</h2>
          <p className="section-subtitle">
            Say what you need in plain English. Nexagent handles browser instantiation, DOM traversal,
            and structured synthesis automatically.
          </p>
        </div>

        <div className="pipeline-steps-grid">
          {/* Step 1 */}
          <div className="pipeline-step-card">
            <div className="step-number">01</div>
            <div className="step-icon-bar">
              <div className="step-mini-icon">
                <Search size={16} color="#2563eb" />
              </div>
            </div>
            <h3 className="step-title">Prompt Your Intent</h3>
            <p className="step-desc">
              Type goals in natural language. Support for complex constraints, localized vernacular,
              or multi-domain retrieval objectives.
            </p>
            <div className="step-code-chip">
              <code>"Find and compare MacBook Air M3 prices across top 3 retailers"</code>
            </div>
          </div>

          {/* Step 2 */}
          <div className="pipeline-step-card">
            <div className="step-number">02</div>
            <div className="step-icon-bar">
              <div className="step-mini-icon">
                <Cpu size={16} color="#059669" />
              </div>
            </div>
            <h3 className="step-title">Agent Executes in Isolated VM</h3>
            <p className="step-desc">
              Nexagent launches an isolated Chromium browser instance, analyzing DOM nodes
              and executing actions autonomously.
            </p>
            <div className="step-code-chip status-chip">
              <code>&gt; Chromium Started in 32ms • Context Isolated</code>
            </div>
          </div>

          {/* Step 3 */}
          <div className="pipeline-step-card">
            <div className="step-number">03</div>
            <div className="step-icon-bar">
              <div className="step-mini-icon">
                <Layers size={16} color="#7c3aed" />
              </div>
            </div>
            <h3 className="step-title">Structured Intelligence</h3>
            <p className="step-desc">
              Inspect verified results in the live inspector, copy structured JSON payloads,
              or review step audit trails and browser screenshots.
            </p>
            <div className="step-code-chip ready-chip">
              <code>200 OK • Payload Deserialized to Typed JSON Model</code>
            </div>
          </div>
        </div>
      </section>

      {/* Explore Common Agent Missions */}
      <section id="missions" className="home-section-missions">
        <div className="section-header-split">
          <div>
            <div className="section-pill">TEST THE ENGINE</div>
            <h2 className="section-title">Explore Common Agent Missions</h2>
            <p className="section-subtitle">
              Select a sample mission below to test the agent engine live in your workspace.
            </p>
          </div>
          <button className="link-all-missions" onClick={() => onGetStarted()}>
            Open custom agent prompt <ArrowRight size={14} />
          </button>
        </div>

        <div className="missions-grid">
          {/* Mission 1 */}
          <div
            className="mission-card"
            onClick={() => onSelectMission("Search and compare current prices for MacBook Air M3 on Amazon and Newegg")}
          >
            <div className="mission-icon-box">
              <Search size={18} color="#2563eb" />
            </div>
            <h4 className="mission-title">E-Commerce Price Scout</h4>
            <p className="mission-desc">
              Search and extract live item specs, price differences, and vendor reputation.
            </p>
            <div className="mission-action">
              <span>Run Mission</span>
              <ArrowRight size={14} />
            </div>
          </div>

          {/* Mission 2 */}
          <div
            className="mission-card"
            onClick={() => onSelectMission("Visit TechCrunch and summarize the top 3 AI breakthrough articles published this week")}
          >
            <div className="mission-icon-box">
              <TrendingUp size={18} color="#059669" />
            </div>
            <h4 className="mission-title">Competitive Intelligence</h4>
            <p className="mission-desc">
              Extract competitor pricing plans, feature roadmaps, and product launches.
            </p>
            <div className="mission-action">
              <span>Run Mission</span>
              <ArrowRight size={14} />
            </div>
          </div>

          {/* Mission 3 */}
          <div
            className="mission-card"
            onClick={() => onSelectMission("Search Google Flights for round-trip flights from NYC to London next month and report lowest fares")}
          >
            <div className="mission-icon-box">
              <Compass size={18} color="#0891b2" />
            </div>
            <h4 className="mission-title">Flight Matrix Tracker</h4>
            <p className="mission-desc">
              Traverse complex calendar date pickers, baggage options, and ticket classes.
            </p>
            <div className="mission-action">
              <span>Run Mission</span>
              <ArrowRight size={14} />
            </div>
          </div>

          {/* Mission 4 */}
          <div
            className="mission-card"
            onClick={() => onSelectMission("Search BBC News for latest global technology announcements and extract structured summary")}
          >
            <div className="mission-icon-box">
              <Newspaper size={18} color="#7c3aed" />
            </div>
            <h4 className="mission-title">Deep Intel &amp; News Feed</h4>
            <p className="mission-desc">
              Aggregate authoritative news across global portals and synthesize insights.
            </p>
            <div className="mission-action">
              <span>Run Mission</span>
              <ArrowRight size={14} />
            </div>
          </div>
        </div>
      </section>


      {/* Bottom CTA Banner (User specified: Not automate task like n8n, this is web agent; and add get started button) */}
      <section className="home-cta-banner-wrapper">
        <div className="home-cta-card">
          <div className="cta-glow-bg" />
          <div className="cta-pill">NEXAGENT WORKSPACE</div>
          <h2 className="cta-title">
            Ready to Run NexAgent Tasks?
          </h2>
          <p className="cta-desc">
            Give your AI full browser agency. Navigate interactive websites, reason through dynamic pages,
            and execute complex multi-step web missions with real-time vision and DOM intelligence.
          </p>

          <form className="cta-form" onSubmit={handleCtaSubmit}>
            <input
              type="text"
              placeholder="Enter your email or target web goal..."
              value={ctaEmail}
              onChange={(e) => setCtaEmail(e.target.value)}
              className="cta-input"
            />
            <button type="submit" className="cta-btn-submit">
              Get Started <ArrowRight size={16} />
            </button>
          </form>

          <div className="cta-badges-row">
            <span>✓ Free task runs included</span>
            <span>✓ Real-time live browser preview</span>
            <span>✓ Zero browser extension required</span>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="home-footer">
        <div className="home-footer-inner">
          <div className="footer-col-brand">
            <div className="footer-brand">
              <img src="/logo.png" alt="Nexagent" className="footer-brand-img" />
              <span className="footer-brand-title">Nexagent</span>
            </div>
            <p className="footer-desc">
              NexAgent intelligent browser automation. Give the agent any web task to browse, inspect,
              navigate, and extract structured data in real time.
            </p>
            <div className="footer-status-pills">
              <span className="status-dot-green" />
              <span>All Systems Operational</span>
            </div>
          </div>

          <div className="footer-col">
            <h5>PRODUCT</h5>
            <ul>
              <li><a href="#features">Autonomous Core</a></li>
              <li><a href="#interactive-demo">Live Viewport</a></li>
              <li><a href="#features">Visual DOM Perception</a></li>
              <li><a href="#missions">Pricing Tiers</a></li>
              <li><a href="#missions">Fleet Telemetry</a></li>
            </ul>
          </div>

          <div className="footer-col">
            <h5>DEVELOPERS</h5>
            <ul>
              <li><a href="#features">Documentation</a></li>
              <li><a href="#features">Browser CDP</a></li>
              <li><a href="#how-it-works">Python SDK</a></li>
              <li><a href="#how-it-works">REST API Reference</a></li>
              <li><a href="#features">System Status</a></li>
            </ul>
          </div>

          <div className="footer-col">
            <h5>TRUST &amp; ENTERPRISE</h5>
            <ul>
              <li><a href="#privacy" onClick={(e) => e.preventDefault()}>Security Whitepaper</a></li>
              <li><a href="#privacy" onClick={(e) => e.preventDefault()}>Privacy Policy</a></li>
              <li><a href="#terms" onClick={(e) => e.preventDefault()}>Terms of Service</a></li>
              <li><a href="#compliance" onClick={(e) => e.preventDefault()}>Compliance Center</a></li>
            </ul>
          </div>
        </div>

        <div className="footer-bottom-bar">
          <div className="footer-copyright">
            © 2026 Nexagent Inc. All permissions and patents reserved.
          </div>
          <div className="footer-bottom-links">
            <a href="#privacy" onClick={(e) => e.preventDefault()}>Privacy</a>
            <a href="#terms" onClick={(e) => e.preventDefault()}>Terms</a>
            <a href="#security" onClick={(e) => e.preventDefault()}>Security</a>
            <a href="#status" onClick={(e) => e.preventDefault()}>Status</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
