/**
 * Configuration Service API
 * Handles all configuration-related API calls
 */

import { httpClient } from './httpClient';
import { API_CONFIG } from './config';
import { ApiDataNode } from '../../model/ApiDataNode';
import { camelize } from '../../shared/utils/camelize';
import { snakeize } from '../../shared/utils/snakeize';

const baseUrl = API_CONFIG.CONFIGURATION_BASE_URL;

export const configurationService = {
  /**
   * Get all nodes
   */
  getNodes: async (): Promise<ApiDataNode[]> => {
    const response = await httpClient.get<{ nodes: unknown[] }>(
      `${baseUrl}${API_CONFIG.ENDPOINTS.CONFIGURATION.NODES}/`
    );
    return camelize(response.nodes) as ApiDataNode[];
  },

  /**
   * Get a single node by ID
   */
  getNode: async (id: string): Promise<ApiDataNode> => {
    const response = await httpClient.get<unknown>(
      `${baseUrl}${API_CONFIG.ENDPOINTS.CONFIGURATION.NODE_BY_ID(id)}`
    );
    return camelize(response) as ApiDataNode;
  },

  /**
   * Create a new node
   */
  createNode: async (node: ApiDataNode): Promise<ApiDataNode> => {
    const data = snakeize(node);
    data.id = null;

    const response = await httpClient.post<unknown>(
      `${baseUrl}${API_CONFIG.ENDPOINTS.CONFIGURATION.NODES}/`,
      data
    );
    return camelize(response) as ApiDataNode;
  },

  /**
   * Update an existing node
   */
  updateNode: async (id: string, node: ApiDataNode): Promise<ApiDataNode> => {
    const response = await httpClient.put<unknown>(
      `${baseUrl}${API_CONFIG.ENDPOINTS.CONFIGURATION.NODE_BY_ID(id)}`,
      snakeize(node)
    );
    return camelize(response) as ApiDataNode;
  },

  /**
   * Delete a node
   */
  deleteNode: async (id: string): Promise<void> => {
    await httpClient.delete(`${baseUrl}${API_CONFIG.ENDPOINTS.CONFIGURATION.NODE_BY_ID(id)}`);
  },

  /**
   * Get children of a node
   */
  getNodeChildren: async (id: string): Promise<ApiDataNode[]> => {
    const response = await httpClient.get<{ nodes: unknown[] }>(
      `${baseUrl}${API_CONFIG.ENDPOINTS.CONFIGURATION.NODE_CHILDREN(id)}`
    );
    return camelize(response.nodes) as ApiDataNode[];
  },
};
