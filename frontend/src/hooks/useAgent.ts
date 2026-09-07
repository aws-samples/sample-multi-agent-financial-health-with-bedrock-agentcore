// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useCallback, useRef } from 'react';
import { fetchAuthSession } from 'aws-amplify/auth';

async function getToken(): Promise<string> {
  const session = await fetchAuthSession();
  return session.tokens?.idToken?.toString() || '';
}

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface UseAgentReturn {
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (prompt: string, context?: Record<string, unknown>) => Promise<void>;
  addMessage: (role: 'user' | 'assistant', content: string) => void;
  clearMessages: () => void;
  sessionIdRef: React.MutableRefObject<string | null>;
}

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:3001';
const POLL_INTERVAL = 5000;
const MAX_POLLS = 60;

interface JobResult {
  job_id: string;
  status: string;
  session_id?: string;
  success?: boolean;
  result?: string;
  usuario_id?: string;
  error?: string;
}

async function pollJob(jobId: string): Promise<JobResult> {
  for (let i = 0; i < MAX_POLLS; i++) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL));
    const token = await getToken();
    const res = await fetch(`${API_URL}/job/${jobId}`, { headers: { 'Authorization': token } });
    if (!res.ok) continue;
    const data = await res.json();
    if (data.status === 'COMPLETED' || data.status === 'FAILED') return data;
  }
  throw new Error('Timeout: el procesamiento tardó demasiado');
}

export function useAgent(userId: string = 'default_user', externalSessionIdRef?: React.MutableRefObject<string | null>): UseAgentReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const internalSessionIdRef = useRef<string | null>(null);
  const sessionIdRef = externalSessionIdRef || internalSessionIdRef;

  const addMessage = useCallback((role: 'user' | 'assistant', content: string) => {
    setMessages(prev => [...prev, { role, content, timestamp: new Date() }]);
  }, []);

  const sendMessage = useCallback(async (prompt: string, context?: Record<string, unknown>) => {
    setIsLoading(true);
    setError(null);

    setMessages(prev => [...prev, { role: 'user', content: prompt, timestamp: new Date() }]);

    try {
      // Step 1: Dispatch
      const token = await getToken();
      const response = await fetch(`${API_URL}/invoke`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': token },
        body: JSON.stringify({
          prompt,
          usuario_id: userId,
          ...(context && { contexto: context }),
          ...(sessionIdRef.current && { session_id: sessionIdRef.current }),
        })
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const dispatch = await response.json();
      if (!dispatch.success) throw new Error(dispatch.error || 'Error desconocido');

      // Step 2: Poll for result
      const data: JobResult = await pollJob(dispatch.job_id);

      if (data.status === 'FAILED') throw new Error(data.error || 'Error en el procesamiento');
      if (data.session_id) sessionIdRef.current = data.session_id;

      setMessages(prev => [...prev, {
        role: 'assistant' as const,
        content: data.result || 'Sin respuesta',
        timestamp: new Date(),
      }]);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Error desconocido';
      setError(errorMessage);
      console.error('Error al invocar agente:', err);
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
    sessionIdRef.current = null;
  }, []);

  return { messages, isLoading, error, sendMessage, addMessage, clearMessages, sessionIdRef };
}
