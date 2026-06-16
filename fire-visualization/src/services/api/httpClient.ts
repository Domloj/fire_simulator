/**
 * HTTP Client with error handling and logging
 */

export interface ApiError {
  message: string;
  status?: number;
  statusText?: string;
  url?: string;
  data?: unknown;
}

export class HttpClientError extends Error {
  status?: number;
  statusText?: string;
  url?: string;
  data?: unknown;

  constructor(error: ApiError) {
    super(error.message);
    this.name = 'HttpClientError';
    this.status = error.status;
    this.statusText = error.statusText;
    this.url = error.url;
    this.data = error.data;
  }
}

const logError = (error: ApiError): void => {
  return; // Disable logging for now
};

async function handleResponse<T>(response: Response, url: string): Promise<T> {
  if (!response.ok) {
    let errorData: unknown = null;
    try {
      const contentType = response.headers.get('content-type');
      if (contentType?.includes('application/json')) {
        errorData = await response.json();
      } else {
        errorData = await response.text();
      }
    } catch (e) {
      // Ignore parsing errors
    }

    const error: ApiError = {
      message: `Request failed: ${response.statusText}`,
      status: response.status,
      statusText: response.statusText,
      url,
      data: errorData,
    };

    logError(error);

    // Handle specific error cases
    if (response.status === 404) {
      throw new HttpClientError({
        ...error,
        message: `Resource not found: ${url}`,
      });
    }

    if (response.status >= 500) {
      throw new HttpClientError({
        ...error,
        message: `Server error: ${response.statusText}`,
      });
    }

    throw new HttpClientError(error);
  }

  // Handle empty responses
  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    return null as T;
  }

  try {
    return await response.json();
  } catch (e) {
    const error: ApiError = {
      message: `Failed to parse JSON response from ${url}`,
      url,
    };
    logError(error);
    throw new HttpClientError(error);
  }

  }

export const httpClient = {
  async get<T>(url: string, options?: RequestInit): Promise<T> {
    try {
      const response = await fetch(url, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
      });

      return handleResponse<T>(response, url);
    } catch (error) {
      if (error instanceof HttpClientError) {
        throw error;
      }

      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error',
        url,
      };
      logError(apiError);
      throw new HttpClientError(apiError);
    }
  },

  async post<T>(url: string, body?: unknown, options?: RequestInit): Promise<T> {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        body: body ? JSON.stringify(body) : undefined,
        ...options,
      });

      return handleResponse<T>(response, url);
    } catch (error) {
      if (error instanceof HttpClientError) {
        throw error;
      }

      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error',
        url,
      };
      logError(apiError);
      throw new HttpClientError(apiError);
    }
  },

  async put<T>(url: string, body?: unknown, options?: RequestInit): Promise<T> {
    try {
      const response = await fetch(url, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        body: body ? JSON.stringify(body) : undefined,
        ...options,
      });

      return handleResponse<T>(response, url);
    } catch (error) {
      if (error instanceof HttpClientError) {
        throw error;
      }

      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error',
        url,
      };
      logError(apiError);
      throw new HttpClientError(apiError);
    }
  },

  async delete<T>(url: string, options?: RequestInit): Promise<T> {
    try {
      const response = await fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
      });

      return handleResponse<T>(response, url);
    } catch (error) {
      if (error instanceof HttpClientError) {
        throw error;
      }

      const apiError: ApiError = {
        message: error instanceof Error ? error.message : 'Network error',
        url,
      };
      logError(apiError);
      throw new HttpClientError(apiError);
    }
  },
};
