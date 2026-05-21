/**
 * Centralized axios instance with automatic Authorization header injection
 * Ensures all API requests include the Firebase ID token
 */

import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const TOKEN_KEY = 'trippy_id_token';

/**
 * Get the current Firebase ID token from localStorage
 */
function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * Create a configured axios instance with automatic Authorization header
 */
function createApiClient(): AxiosInstance {
  const client = axios.create({
    baseURL: API_BASE,
    timeout: 15000,
  });

  /**
   * Request interceptor: automatically add Authorization header if token exists
   */
  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = getToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error) => Promise.reject(error)
  );

  /**
   * Response interceptor: handle 401 Unauthorized by refreshing token if possible
   */
  client.interceptors.response.use(
    (response) => response,
    async (error) => {
      const originalRequest = error.config;

      // Handle 401 Unauthorized
      if (error.response?.status === 401 && !originalRequest._retry) {
        originalRequest._retry = true;

        try {
          const refreshToken = localStorage.getItem('trippy_refresh_token');
          if (refreshToken) {
            // Try to refresh the token
            const response = await axios.post(`${API_BASE}/api/auth/refresh`, {
              refresh_token: refreshToken,
            });

            const { id_token } = response.data;
            localStorage.setItem(TOKEN_KEY, id_token);

            // Retry the original request with the new token
            originalRequest.headers.Authorization = `Bearer ${id_token}`;
            return client(originalRequest);
          }
        } catch (refreshError) {
          // Refresh failed, redirect to login
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem('trippy_refresh_token');
          localStorage.removeItem('trippy_user');
          window.location.href = '/';
          return Promise.reject(refreshError);
        }
      }

      return Promise.reject(error);
    }
  );

  return client;
}

export const apiClient = createApiClient();
