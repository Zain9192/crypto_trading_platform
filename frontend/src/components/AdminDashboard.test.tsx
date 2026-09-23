import '@testing-library/jest-dom/vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import AdminDashboard from './AdminDashboard'
import { ApiError } from '../api/portfolio'

afterEach(cleanup)
it('hides privileged data if any admin request loses authorization', async () => {
  const request=vi.fn(async () => { throw new ApiError('Forbidden',403) })
  render(<QueryClientProvider client={new QueryClient({ defaultOptions:{queries:{retry:false}} })}><AdminDashboard request={request as never} /></QueryClientProvider>)
  expect(await screen.findByRole('alert')).toHaveTextContent('Administrator access is no longer available')
  expect(screen.queryByRole('button',{name:'Check storage and providers'})).not.toBeInTheDocument()
})
it('renders untrusted usernames as text, never HTML', async () => {
  const request=vi.fn(async (path:string) => {
    if(path.startsWith('/admin/users')) return {items:[{user_id:1,username:'<img src=x onerror=alert(1)>',email:'x@example.test',role:'trader',is_active:true}],next_cursor:null}
    if(path.startsWith('/admin/models') || path.startsWith('/admin/audit')) return {items:[],next_cursor:null}
    if(path==='/admin/operations') return {bots:[],exchanges:[]}
    return {users_total:1,users_active:1}
  })
  const {container}=render(<QueryClientProvider client={new QueryClient()}><AdminDashboard request={request as never} /></QueryClientProvider>)
  expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument()
  expect(container.querySelector('img')).toBeNull()
})
