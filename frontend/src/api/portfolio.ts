export type DecimalString = string
export interface Tokens { access_token: string; refresh_token: string; expires_in: number }
export interface RiskSettings {
  min_investment: string; max_investment: string; max_open_positions: number; max_open_trades: number
  stop_loss_pct: string | null; take_profit_pct: string | null
}
export interface Order {
  order_id: string; symbol: string; side: 'buy' | 'sell'; quantity: string; simulation_price: string
  fee: string; status: string; stop_loss_price: string | null; take_profit_price: string | null
}
export interface Holding {
  symbol: string; quantity: string; available_quantity: string; cost_basis: string; average_cost: string
  market_value: string | null; unrealized_pnl: string | null; allocation_pct: string | null; price_as_of: string | null
}
export interface Portfolio {
  portfolio_id: number; mode: 'paper'; initial_cash: string; cash_balance: string; available_cash: string; reserved_cash: string
  total_value: string | null; realized_pnl: string; unrealized_pnl: string | null; total_pnl: string | null
  cash_allocation_pct: string | null; valuation_complete: boolean; unpriced_symbols: string[]
  holdings: Holding[]; pending_orders: Order[]; risk_settings: RiskSettings
}
export interface Trade {
  trade_id: number; symbol: string; side: string; quantity: string; price: string; fee: string; realized_pnl: string; created_at: string
}
export interface History { items: Trade[]; next_cursor: number | null }
export interface PaperRequest { client_order_id: string; symbol: string; side: string; quantity: string; simulation_price: string; fee: string }
export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message) }
}
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
export async function api<T>(path: string, token?: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method, headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = payload?.detail
    const message = typeof detail === 'string' ? detail : Array.isArray(detail)
      ? detail.map((item: { loc?: string[]; msg: string }) => `${item.loc?.slice(1).join('.') ?? 'Input'}: ${item.msg}`).join('; ')
      : `Request failed (${response.status})`
    throw new ApiError(message, response.status)
  }
  return payload as T
}
