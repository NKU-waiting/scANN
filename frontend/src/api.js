let tokenProvider = () => localStorage.getItem('scann_token') || ''
let unauthorizedHandler = () => {}

export function configureApi({ getToken, onUnauthorized }) {
  if (getToken) tokenProvider = getToken
  if (onUnauthorized) unauthorizedHandler = onUnauthorized
}

export async function apiRequest(path, options = {}, authenticated = true) {
  const headers = { Accept: 'application/json', ...(options.headers || {}) }
  const token = tokenProvider()
  if (authenticated && token) headers.Authorization = `Bearer ${token}`
  if (options.body && !(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  let response
  try {
    response = await fetch(path, { ...options, headers })
  } catch {
    throw new Error('无法连接后端服务，请确认服务已启动')
  }

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { error: text }
    }
  }
  if (response.status === 401 && authenticated) unauthorizedHandler(token)
  if (!response.ok) throw new Error(data?.error || `请求失败（${response.status}）`)
  return data
}
