/**
 * API サービスファイル
 */

import { ApiResponse, User, Device, CSIData, BreathingAnalysis } from '@/types'

// API Base URL
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?
  `${process.env.NEXT_PUBLIC_API_URL}/api/v2` :
  'http://192.168.101.168:8000/api/v2'

// APIクライアントクラス
class ApiClient {
  private baseURL: string
  private token: string | null = null

  constructor(baseURL: string) {
    this.baseURL = baseURL
    // ローカルストレージからトークンを取得
    if (typeof window !== 'undefined') {
      this.token = localStorage.getItem('access_token')
    }
  }

  // 認証トークンを設定
  setToken(token: string) {
    this.token = token
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', token)
    }
  }

  // 認証トークンを削除
  clearToken() {
    this.token = null
    if (typeof window !== 'undefined') {
      localStorage.removeItem('access_token')
    }
  }

  // HTTP リクエストの基本メソッド
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const url = `${this.baseURL}${endpoint}`

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      ...options.headers,
    }

    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const data = await response.json()
      return data
    } catch (error) {
      console.error('API request failed:', error)
      throw error
    }
  }

  // GET リクエスト
  async get<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'GET' })
  }

  // POST リクエスト
  async post<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  // PUT リクエスト
  async put<T>(endpoint: string, data?: any): Promise<T> {
    return this.request<T>(endpoint, {
      method: 'PUT',
      body: data ? JSON.stringify(data) : undefined,
    })
  }

  // DELETE リクエスト
  async delete<T>(endpoint: string): Promise<T> {
    return this.request<T>(endpoint, { method: 'DELETE' })
  }

  // ファイルアップロード
  async upload<T>(endpoint: string, formData: FormData): Promise<T> {
    const url = `${this.baseURL}${endpoint}`

    const headers: HeadersInit = {}
    if (this.token) {
      headers.Authorization = `Bearer ${this.token}`
    }

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    })

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`)
    }

    return response.json()
  }

  // 認証関連
  async login(username: string, password: string) {
    const response = await this.post<{ access_token: string; token_type: string }>('/auth/login', {
      username,
      password,
    })
    this.setToken(response.access_token)
    return response
  }

  async register(username: string, email: string, password: string) {
    return this.post<ApiResponse<User>>('/auth/register', {
      username,
      email,
      password,
    })
  }

  async logout() {
    try {
      await this.post('/auth/logout')
    } finally {
      this.clearToken()
    }
  }

  // ユーザー関連
  async getCurrentUser(): Promise<User> {
    return this.get<User>('/auth/me')
  }

  async updateProfile(profileData: { username?: string; email?: string }): Promise<User> {
    return this.put<User>('/users/me', profileData)
  }

  async requestPasswordReset(email: string): Promise<{ message: string }> {
    return this.post<{ message: string }>('/auth/password-reset/request', { email })
  }

  async resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
    return this.post<{ message: string }>('/auth/password-reset/confirm', {
      token,
      new_password: newPassword
    })
  }

  // デバイス関連
  async getDevices(params?: URLSearchParams): Promise<any> {
    const endpoint = params ? `/devices/?${params.toString()}` : '/devices/'
    return this.get<any>(endpoint)
  }

  async getDevice(deviceId: string): Promise<Device> {
    return this.get<Device>(`/devices/${deviceId}`)
  }

  async createDevice(deviceData: any): Promise<Device> {
    return this.post<Device>('/devices', deviceData)
  }

  async updateDevice(deviceId: string, deviceData: Partial<Device>): Promise<Device> {
    return this.put<Device>(`/devices/${deviceId}`, deviceData)
  }

  async deleteDevice(deviceId: string): Promise<void> {
    return this.delete<void>(`/devices/${deviceId}`)
  }

  async getDeviceStatus(deviceId: string): Promise<any> {
    return this.get<any>(`/devices/${deviceId}/status`)
  }

  async sendDeviceHeartbeat(deviceId: string, heartbeatData: any): Promise<Device> {
    return this.post<Device>(`/devices/${deviceId}/heartbeat`, heartbeatData)
  }

  async getDeviceStatistics(): Promise<any> {
    return this.get<any>('/devices/statistics/summary')
  }

  // CSIデータ関連
  async uploadCSIData(deviceId: string, file: File): Promise<CSIData> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('device_id', deviceId)

    return this.upload<CSIData>('/csi-data/upload', formData)
  }

  async getCSIData(deviceId: string): Promise<CSIData[]> {
    return this.get<CSIData[]>(`/csi-data/${deviceId}`)
  }

  async getLatestCSIData(deviceId: string): Promise<CSIData> {
    return this.get<CSIData>(`/csi-data/${deviceId}/latest`)
  }

  // 呼吸解析関連
  async getBreathingAnalysis(deviceId: string): Promise<BreathingAnalysis[]> {
    return this.get<BreathingAnalysis[]>(`/breathing-analysis/results/${deviceId}`)
  }

  async getLatestBreathingAnalysis(deviceId: string): Promise<BreathingAnalysis> {
    return this.get<BreathingAnalysis>(`/breathing-analysis/results/${deviceId}/latest`)
  }

  // ヘルスチェック関連
  async healthCheck() {
    return this.get('/health')
  }

  // CSIデータ関連
  async uploadCSIData(deviceId: string, file: File, metadata?: any): Promise<any> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('device_id', deviceId)
    if (metadata) {
      formData.append('metadata', JSON.stringify(metadata))
    }

    return this.upload('/csi-data/upload', formData)
  }

  async getCSIDataList(params?: URLSearchParams): Promise<any> {
    const endpoint = params ? `/csi-data/?${params.toString()}` : '/csi-data/'
    return this.get(endpoint)
  }

  async getCSIData(csiDataId: string): Promise<any> {
    return this.get(`/csi-data/${csiDataId}`)
  }

  async deleteCSIData(csiDataId: string): Promise<void> {
    return this.delete(`/csi-data/${csiDataId}`)
  }

  async getCSIStats(deviceId: string, days: number = 7): Promise<any> {
    return this.get(`/csi-data/${deviceId}/stats?days=${days}`)
  }

  async getCSIVisualizationData(csiDataId: string, params?: URLSearchParams): Promise<any> {
    const endpoint = params
      ? `/csi-data/${csiDataId}/visualization?${params.toString()}`
      : `/csi-data/${csiDataId}/visualization`
    return this.get(endpoint)
  }

  // 呼吸解析関連
  async getBreathingAnalysis(deviceId: string, params?: URLSearchParams): Promise<any> {
    const endpoint = params ? `/breathing-analysis/results/${deviceId}?${params.toString()}` : `/breathing-analysis/results/${deviceId}`
    return this.get(endpoint)
  }

  async getLatestBreathingAnalysis(deviceId: string): Promise<any> {
    return this.get(`/breathing-analysis/results/${deviceId}/latest`)
  }

  async getBreathingTrends(deviceId: string, hours: number = 24): Promise<any> {
    return this.get(`/breathing-analysis/trends/${deviceId}?hours=${hours}`)
  }
}

// APIクライアントのインスタンス
export const apiClient = new ApiClient(API_BASE_URL)

// 便利な関数をエクスポート
export const api = {
  auth: {
    login: (username: string, password: string) => apiClient.login(username, password),
    register: (username: string, email: string, password: string) => apiClient.register(username, email, password),
    logout: () => apiClient.logout(),
    getCurrentUser: () => apiClient.getCurrentUser(),
    requestPasswordReset: (email: string) => apiClient.requestPasswordReset(email),
    resetPassword: (token: string, newPassword: string) => apiClient.resetPassword(token, newPassword),
  },
  users: {
    updateProfile: (data: { username?: string; email?: string }) => apiClient.updateProfile(data),
  },
  devices: {
    list: (params?: URLSearchParams) => apiClient.getDevices(params),
    get: (id: string) => apiClient.getDevice(id),
    create: (data: any) => apiClient.createDevice(data),
    update: (id: string, data: Partial<Device>) => apiClient.updateDevice(id, data),
    delete: (id: string) => apiClient.deleteDevice(id),
    status: (id: string) => apiClient.getDeviceStatus(id),
    heartbeat: (id: string, data: any) => apiClient.sendDeviceHeartbeat(id, data),
    statistics: () => apiClient.getDeviceStatistics(),
  },
  csi: {
    upload: (deviceId: string, file: File) => apiClient.uploadCSIData(deviceId, file),
    list: (deviceId: string) => apiClient.getCSIData(deviceId),
    latest: (deviceId: string) => apiClient.getLatestCSIData(deviceId),
  },
  breathing: {
    list: (deviceId: string) => apiClient.getBreathingAnalysis(deviceId),
    latest: (deviceId: string) => apiClient.getLatestBreathingAnalysis(deviceId),
  },
  health: () => apiClient.healthCheck(),
}