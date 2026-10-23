import { useEffect, useMemo, useState } from 'react'
import {
  Activity, BarChart3, ChevronRight, CircleDollarSign, Gauge, LayoutDashboard,
  ListFilter, Menu, Pause, Play, RefreshCw, Settings, ShieldCheck, TrendingUp,
  X, Zap
} from 'lucide-react'

const API = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

type Opportunity = {
  symbol: string
  buy_exchange: string
  sell_exchange: string
  buy_price: number
  sell_price: number
  quantity: number
  position_size: number
  liquidity_ok: boolean
  book_age: number
  risk_level: string
  net_profit_usd: number
  net_profit_pct: number
  gross_profit_usd: number
  gross_profit_pct: number
  total_fees_usd: number
  fees_pct: number
  slippage_usd: number
  slippage_pct: number
  timestamp: number
  execution_supported?: boolean
}

type Status = {
  status: string
  started: boolean
  mode: string
  live_trading: boolean
  auto_execute: boolean
  symbols: string[]
  max_trade_size_usd: number
  engine: {
    running: boolean
    capital_usd: number
    last_scan_at: number
    execution_count: number
    error_count: number
  }
}

type ScannerDiagnostic = {
  status: string
  books_available: number
  exchanges_configured: number
  evaluated_routes: number
  gross_positive_routes: number
  positive_opportunities: number
  nonpositive_net_routes: number
  insufficient_liquidity_routes: number
  below_minimum_size_routes: number
  max_gross_profit_pct: number | null
  max_net_profit_pct: number | null
  estimated_slippage_pct: number
  stale_or_empty_exchanges: Record<string, string>
  exchange_errors: Record<string, string>
  best_gross_candidate: null | {
    buy_exchange: string; sell_exchange: string; gross_profit_pct: number; net_profit_pct: number
    net_profit_usd: number; position_size: number; liquidity_ok: boolean; execution_supported: boolean
  }
}
type Page = 'home' | 'links' | 'stats' | 'trading' | 'risk' | 'settings'

const menu = [
  { id: 'home' as Page, label: 'Главная', icon: LayoutDashboard },
  { id: 'links' as Page, label: 'Связки', icon: Zap },
  { id: 'stats' as Page, label: 'Статистика', icon: BarChart3 },
  { id: 'trading' as Page, label: 'Торговля', icon: TrendingUp },
  { id: 'risk' as Page, label: 'Риск-контроль', icon: ShieldCheck },
  { id: 'settings' as Page, label: 'Настройки', icon: Settings },
]

const fmtMoney = (n: number) => `$${n.toFixed(2)}`
const fmtPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(3)}%`
const exchangeName = (id: string) => ({
  binance: 'Binance', bybit: 'Bybit', kraken: 'Kraken', okx: 'OKX', bitget: 'Bitget', gate: 'Gate.io', kucoin: 'KuCoin'
}[id] || id)

function App() {
  const [page, setPage] = useState<Page>('home')
  const [mobileOpen, setMobileOpen] = useState(false)
  const [opportunities, setOpportunities] = useState<Opportunity[]>([])
  const [diagnostics, setDiagnostics] = useState<Record<string, ScannerDiagnostic>>({})
  const [status, setStatus] = useState<Status | null>(null)
  const [capital, setCapital] = useState('50')
  const [savedCapital, setSavedCapital] = useState(50)
  const [selected, setSelected] = useState<Opportunity | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)

  async function refresh() {
    try {
      setError('')
      const [s, o] = await Promise.all([
        fetch(`${API}/api/status`).then(r => r.json()),
        fetch(`${API}/api/opportunities/live`).then(r => r.json()),
      ])
      setStatus(s)
      const incoming = Array.isArray(o.opportunities) ? o.opportunities : []
      setOpportunities(incoming)
      setDiagnostics(o.diagnostics && typeof o.diagnostics === 'object' ? o.diagnostics : {})
      setLastUpdate(new Date())
      if (s?.engine?.capital_usd) {
        setSavedCapital(Number(s.engine.capital_usd))
        setCapital(String(Number(s.engine.capital_usd)))
      }
    } catch {
      setError('Не удалось подключиться к backend. Проверь, что FastAPI запущен на порту 8000.')
    }
  }

  useEffect(() => {
    refresh()
    const timer = window.setInterval(refresh, 1000)
    return () => window.clearInterval(timer)
  }, [])

  async function saveCapital() {
    const value = Number(capital.replace(',', '.'))
    if (!Number.isFinite(value) || value <= 0) return setError('Введите корректную сумму больше 0.')
    setLoading(true)
    try {
      const response = await fetch(`${API}/api/settings/capital`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ capital_usd: value })
      })
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Ошибка сохранения')
      setSavedCapital(data.capital_usd)
      setCapital(String(data.capital_usd))
      await refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось сохранить сумму')
    } finally { setLoading(false) }
  }

  async function toggleEngine() {
    setLoading(true)
    try {
      const running = status?.engine?.running
      await fetch(`${API}/api/engine/${running ? 'stop' : 'start'}`, { method: 'POST' })
      await refresh()
    } catch { setError('Не удалось изменить состояние двигателя.') }
    finally { setLoading(false) }
  }

  const best = opportunities[0]
  const avgNet = useMemo(() => opportunities.length ? opportunities.reduce((a, x) => a + x.net_profit_pct, 0) / opportunities.length : 0, [opportunities])

  return <div className="app-shell">
    <aside className={`sidebar ${mobileOpen ? 'open' : ''}`}>
      <div className="brand">
        <div className="brand-mark"><Zap size={20} fill="currentColor" /></div>
        <div><b>Arvex</b><span>SPOT ARBITRAGE</span></div>
      </div>
      <div className="side-section-title">РАБОЧАЯ ОБЛАСТЬ</div>
      <nav>
        {menu.map(item => {
          const Icon = item.icon
          return <button key={item.id} className={`nav-item ${page === item.id ? 'active' : ''}`} onClick={() => { setPage(item.id); setMobileOpen(false) }}>
            <Icon size={18}/><span>{item.label}</span>{page === item.id && <ChevronRight size={15} className="nav-arrow"/>}
          </button>
        })}
      </nav>
      <div className="sidebar-bottom">
        <div className="mode-card"><div className="dot"/><div><span>Режим</span><strong>{status?.mode || 'PAPER'}</strong></div></div>
        <div className="connection"><span className="live-dot"/> Backend {error ? 'offline' : 'online'}</div>
      </div>
    </aside>

    <main className="main">
      <header className="topbar">
        <button className="icon-btn mobile-menu" onClick={() => setMobileOpen(v => !v)}><Menu size={20}/></button>
        <div><div className="eyebrow">ARVEX / {page.toUpperCase()}</div><h1>{menu.find(x => x.id === page)?.label}</h1></div>
        <div className="top-actions">
          <div className="live-indicator"><span className="live-dot"/> Сканер</div>
          <button className="icon-btn" onClick={refresh} title="Обновить"><RefreshCw size={18}/></button>
        </div>
      </header>

      {error && <div className="error-banner"><Activity size={17}/>{error}<button onClick={() => setError('')}><X size={16}/></button></div>}

      {page === 'home' && <HomePage best={best} opportunities={opportunities} diagnostics={diagnostics} avgNet={avgNet} status={status} capital={capital} setCapital={setCapital} saveCapital={saveCapital} loading={loading} toggleEngine={toggleEngine} savedCapital={savedCapital} lastUpdate={lastUpdate} open={setSelected} />}
      {page === 'links' && <LinksPage opportunities={opportunities} diagnostics={diagnostics} open={setSelected} capital={savedCapital} />}
      {page === 'stats' && <StatsPage opportunities={opportunities} status={status} />}
      {page === 'trading' && <TradingPage status={status} toggleEngine={toggleEngine} loading={loading} />}
      {page === 'risk' && <RiskPage status={status} capital={savedCapital} />}
      {page === 'settings' && <SettingsPage status={status} capital={capital} setCapital={setCapital} saveCapital={saveCapital} loading={loading} />}
    </main>

    {selected && <OpportunityModal item={selected} onClose={() => setSelected(null)} />}
  </div>
}

function HomePage({ best, opportunities, diagnostics, avgNet, status, capital, setCapital, saveCapital, loading, toggleEngine, savedCapital, lastUpdate, open }: any) {
  return <div className="content">
    <section className="hero-grid">
      <div className="panel capital-panel">
        <div className="panel-head"><div><span className="label">КАПИТАЛ НА СВЯЗКИ</span><h2>Укажи сумму, которую бот может использовать</h2></div><CircleDollarSign className="orange-icon"/></div>
        <div className="capital-input"><span>$</span><input value={capital} onChange={e => setCapital(e.target.value)} onKeyDown={e => e.key === 'Enter' && saveCapital()}/><button onClick={saveCapital} disabled={loading}>{loading ? '...' : 'Сохранить'}</button></div>
        <div className="hint">Лимит безопасности backend: {fmtMoney(status?.max_trade_size_usd ?? 100)}</div>
      </div>
      <div className="panel engine-panel">
        <div className="panel-head"><div><span className="label">ДВИЖОК</span><h2>{status?.engine?.running ? 'Мониторинг активен' : 'Мониторинг остановлен'}</h2></div><Gauge className="orange-icon"/></div>
        <div className="engine-row"><div><span>Режим</span><strong>{status?.mode || 'PAPER'}</strong></div><button className={`engine-btn ${status?.engine?.running ? 'stop' : ''}`} onClick={toggleEngine} disabled={loading}>{status?.engine?.running ? <><Pause size={17}/> Остановить</> : <><Play size={17}/> Запустить</>}</button></div>
      </div>
    </section>

    <section className="metrics-grid">
      <Metric title="Лучший net %" value={best ? fmtPct(best.net_profit_pct) : '—'} accent />
      <Metric title="Чистая прибыль" value={best ? fmtMoney(best.net_profit_usd) : '$0.00'} />
      <Metric title="Доступно связок" value={String(opportunities.length)} />
      <Metric title="Средний net %" value={opportunities.length ? fmtPct(avgNet) : '—'} />
    </section>

    <ScannerDiagnostics diagnostics={diagnostics} />

    <section className="panel links-panel">
      <div className="section-head"><div><span className="label">ТОП ВОЗМОЖНОСТИ</span><h2>Связки с чистым процентом</h2></div><button className="ghost-btn" onClick={() => open(best)} disabled={!best}>Открыть лучшую <ChevronRight size={16}/></button></div>
      <OpportunityTable opportunities={opportunities.slice(0, 8)} open={open}/>
      <div className="table-footer"><span>Последнее обновление: {lastUpdate ? lastUpdate.toLocaleTimeString() : '—'}</span><span>Используется: {fmtMoney(savedCapital)}</span></div>
    </section>
  </div>
}

function LinksPage({ opportunities, diagnostics, open, capital }: { opportunities: Opportunity[]; diagnostics: Record<string, ScannerDiagnostic>; open: (x: Opportunity) => void; capital: number }) {
  return <div className="content"><div className="page-intro"><div><span className="label">АРБИТРАЖНЫЕ СВЯЗКИ</span><h2>Монеты и чистая доходность</h2><p>Показываются только маршруты с положительной чистой прибылью и достаточной ликвидностью.</p></div><div className="capital-pill">Бюджет <b>{fmtMoney(capital)}</b></div></div><ScannerDiagnostics diagnostics={diagnostics}/><div className="panel links-panel"><OpportunityTable opportunities={opportunities} open={open}/></div></div>
}

function StatsPage({ opportunities, status }: { opportunities: Opportunity[]; status: Status | null }) {
  const profit = opportunities.reduce((a, x) => a + x.net_profit_usd, 0)
  const max = opportunities.length ? Math.max(...opportunities.map(x => x.net_profit_pct)) : 0
  return <div className="content"><div className="metrics-grid"><Metric title="Сканирований с ошибкой" value={String(status?.engine.error_count ?? 0)} /><Metric title="Исполнений" value={String(status?.engine.execution_count ?? 0)} /><Metric title="Сумма net по найденным" value={fmtMoney(profit)} /><Metric title="Максимальный net %" value={fmtPct(max)} accent /></div><div className="panel chart-panel"><div className="section-head"><div><span className="label">РАСПРЕДЕЛЕНИЕ</span><h2>Доходность текущих связок</h2></div></div><div className="bars">{opportunities.slice(0, 12).map((x, i) => <div className="bar-row" key={`${x.symbol}-${x.buy_exchange}-${x.sell_exchange}-${i}`}><div className="bar-label"><span>{x.symbol}</span><b>{fmtPct(x.net_profit_pct)}</b></div><div className="bar-track"><div className="bar-fill" style={{width: `${Math.min(100, Math.max(4, x.net_profit_pct * 20))}%`}}/></div></div>)}</div></div></div>
}

function TradingPage({ status, toggleEngine, loading }: any) {
  return <div className="content"><div className="panel big-status"><div className="status-icon"><Activity/></div><div><span className="label">СТАТУС ДВИЖКА</span><h2>{status?.engine.running ? 'Система работает' : 'Система остановлена'}</h2><p>Автовыполнение: <b>{status?.auto_execute ? 'включено' : 'выключено'}</b>. Режим: <b>{status?.mode || 'PAPER'}</b>.</p></div><button className="engine-btn" onClick={toggleEngine} disabled={loading}>{status?.engine.running ? 'Остановить' : 'Запустить'}</button></div><div className="metrics-grid"><Metric title="Монеты" value={String(status?.symbols?.length ?? 0)} /><Metric title="Размер связки" value={fmtMoney(status?.engine?.capital_usd ?? 0)} /><Metric title="Auto execute" value={status?.auto_execute ? 'ON' : 'OFF'} /><Metric title="LIVE trading" value={status?.live_trading ? 'ON' : 'OFF'} /></div></div>
}

function RiskPage({ status, capital }: { status: Status | null; capital: number }) {
  const max = status?.max_trade_size_usd ?? 100
  const percent = Math.min(100, capital / max * 100)
  return <div className="content"><div className="panel risk-card"><div className="risk-title"><ShieldCheck/><div><span className="label">SAFETY ENGINE</span><h2>Контроль размера позиции</h2></div></div><div className="risk-value">{fmtMoney(capital)} <span>/ {fmtMoney(max)}</span></div><div className="risk-track"><div style={{width: `${percent}%`}}/></div><div className="risk-grid"><div><span>Режим</span><b>{status?.mode || 'PAPER'}</b></div><div><span>Текущий бюджет</span><b>{fmtMoney(capital)}</b></div><div><span>Лимит</span><b>{fmtMoney(max)}</b></div></div></div><div className="panel info-list"><h2>Что проверяется перед связкой</h2><div>✓ Чистый процент после комиссий</div><div>✓ Ликвидность стакана под выбранную сумму</div><div>✓ Возраст order book</div><div>✓ Лимиты размера позиции</div><div>✓ Риск-уровень возможности</div></div></div>
}

function SettingsPage({ status, capital, setCapital, saveCapital, loading }: any) {
  return <div className="content"><div className="panel settings-card"><div className="section-head"><div><span className="label">ПАРАМЕТРЫ</span><h2>Настройки связок</h2></div><Settings className="orange-icon"/></div><label>Сумма на одну связку</label><div className="capital-input"><span>$</span><input value={capital} onChange={e => setCapital(e.target.value)}/><button onClick={saveCapital} disabled={loading}>Сохранить</button></div><div className="settings-grid"><div><span>Максимум</span><b>{fmtMoney(status?.max_trade_size_usd ?? 100)}</b></div><div><span>Режим</span><b>{status?.mode || 'PAPER'}</b></div><div><span>Монеты</span><b>{status?.symbols?.join(', ') || '—'}</b></div></div></div></div>
}

function ScannerDiagnostics({ diagnostics }: { diagnostics: Record<string, ScannerDiagnostic> }) {
  const rows = Object.entries(diagnostics)
  const label = (status: string) => ({
    waiting_for_books: 'Ожидаем стаканы минимум двух бирж',
    no_routes_evaluated: 'Нет маршрутов для расчёта',
    no_gross_spread: 'Валовой спред не найден',
    spread_erased_by_costs: 'Спред съеден комиссиями и проскальзыванием',
    liquidity_or_minimum_size: 'Не прошли ликвидность или минимальный размер',
    opportunities_found: 'Есть прибыльные кандидаты',
  }[status] || status)
  return <section className="panel links-panel">
    <div className="section-head"><div><span className="label">ДИАГНОСТИКА СКАНЕРА</span><h2>Почему связок может не быть</h2></div></div>
    {!rows.length && <p>Пока нет данных сканера. Запусти мониторинг и дождись первого обновления стаканов.</p>}
    <div className="metrics-grid">
      {rows.map(([symbol, d]) => <div className="metric" key={symbol}>
        <span>{symbol} · стаканы {d.books_available}/{d.exchanges_configured}</span>
        <strong>{label(d.status)}</strong>
        <small>Маршрутов: {d.evaluated_routes} · валовой плюс: {d.gross_positive_routes} · после расходов в минус: {d.nonpositive_net_routes}</small>
        <small>Макс. gross: {d.max_gross_profit_pct == null ? '—' : fmtPct(d.max_gross_profit_pct)} · макс. net: {d.max_net_profit_pct == null ? '—' : fmtPct(d.max_net_profit_pct)}</small>
        {d.best_gross_candidate && <small>Лучший gross: {exchangeName(d.best_gross_candidate.buy_exchange)} → {exchangeName(d.best_gross_candidate.sell_exchange)}; net {fmtPct(d.best_gross_candidate.net_profit_pct)} ({fmtMoney(d.best_gross_candidate.net_profit_usd)})</small>}
        {Object.keys(d.exchange_errors || {}).length > 0 && <small>Ошибки: {Object.keys(d.exchange_errors).join(', ')}</small>}
        {Object.keys(d.stale_or_empty_exchanges || {}).length > 0 && <small>Нет свежего стакана: {Object.keys(d.stale_or_empty_exchanges).join(', ')}</small>}
      </div>)}
    </div>
  </section>
}

function Metric({ title, value, accent = false }: { title: string; value: string; accent?: boolean }) { return <div className="metric"><span>{title}</span><strong className={accent ? 'accent' : ''}>{value}</strong></div> }

function OpportunityTable({ opportunities, open }: { opportunities: Opportunity[]; open: (x: Opportunity) => void }) {
  if (!opportunities.length) return <div className="empty"><ListFilter size={22}/><div><b>Пока нет подходящих связок</b><span>Сканер показывает только маршруты с положительной чистой прибылью; причины отсева смотри в диагностике выше.</span></div></div>
  return <div className="table-wrap"><table><thead><tr><th>Монета</th><th>Направление</th><th>Чистый %</th><th>Чистая прибыль</th><th>Сумма</th><th>Риск</th><th></th></tr></thead><tbody>{opportunities.map((x, i) => <tr key={`${x.symbol}-${x.buy_exchange}-${x.sell_exchange}-${i}`} onClick={() => open(x)}><td><div className="coin"><span>{x.symbol.replace('USDT','')}</span><small>USDT</small></div></td><td><div><div className="route"><b>{exchangeName(x.buy_exchange)}</b><ChevronRight size={14}/><b>{exchangeName(x.sell_exchange)}</b></div>{x.execution_supported === false && <small>Только мониторинг</small>}</div></td><td><strong className="profit">{fmtPct(x.net_profit_pct)}</strong></td><td><strong>{fmtMoney(x.net_profit_usd)}</strong></td><td>{fmtMoney(x.position_size)}</td><td><span className={`risk ${x.risk_level.toLowerCase()}`}>{x.risk_level === 'SAFE_CANDIDATE' ? 'SAFE' : x.risk_level}</span></td><td><ChevronRight size={17} className="row-arrow"/></td></tr>)}</tbody></table></div>
}

function OpportunityModal({ item, onClose }: { item: Opportunity; onClose: () => void }) {
  return <div className="modal-backdrop" onClick={onClose}><div className="modal" onClick={e => e.stopPropagation()}><div className="modal-head"><div><span className="label">ДЕТАЛИ СВЯЗКИ</span><h2>{item.symbol}</h2></div><button className="icon-btn" onClick={onClose}><X size={19}/></button></div><div className="route-card"><div><span>ПОКУПКА</span><b>{exchangeName(item.buy_exchange)}</b><small>${item.buy_price.toFixed(6)}</small></div><ChevronRight className="route-chevron"/><div><span>ПРОДАЖА</span><b>{exchangeName(item.sell_exchange)}</b><small>${item.sell_price.toFixed(6)}</small></div></div><div className="net-card"><span>ЧИСТАЯ ДОХОДНОСТЬ</span><strong>{fmtPct(item.net_profit_pct)}</strong><b>{fmtMoney(item.net_profit_usd)}</b></div><div className="detail-grid"><Detail label="Размер" value={fmtMoney(item.position_size)}/><Detail label="Количество" value={item.quantity.toFixed(6)}/><Detail label="Комиссии" value={`${fmtMoney(item.total_fees_usd)} (${item.fees_pct.toFixed(3)}%)`}/><Detail label="Проскальзывание" value={`${fmtMoney(item.slippage_usd)} (${item.slippage_pct.toFixed(3)}%)`}/><Detail label="Ликвидность" value={item.liquidity_ok ? 'OK' : 'Недостаточно'}/><Detail label="Возраст стакана" value={`${item.book_age.toFixed(2)} сек`}/></div><div className="modal-note">{item.execution_supported === false ? "Это только рыночный кандидат: котировки доступны, но торговое исполнение через ArbX для одной или обеих бирж не реализовано. Не отправляй этот маршрут на исполнение." : "Чистый процент берётся из backend и не является гарантированной фактической прибылью до подтверждения исполнения обеих ног."}</div></div></div>
}
function Detail({ label, value }: { label: string; value: string }) { return <div className="detail"><span>{label}</span><b>{value}</b></div> }

export default App
