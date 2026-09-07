// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0
import React, { useState, useRef, useEffect, forwardRef, useImperativeHandle } from 'react';
import { useAgent } from '../hooks/useAgent';
import { parseResponse } from '../utils/parseResponse';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkBreaks from 'remark-breaks';
import { Icon } from './Icon';
import type { Components } from 'react-markdown';
import type { ChartBlock } from '../utils/parseResponse';

// GFM tables/strikethrough + single-newline line breaks (matches the previous
// marked { gfm: true, breaks: true } behavior).
const MARKDOWN_PLUGINS = [remarkGfm, remarkBreaks];

// react-markdown renders to React nodes and never injects raw HTML, so there is
// no XSS sink here. Links are additionally forced to open safely.
const MARKDOWN_COMPONENTS: Components = {
  a: ({ node: _node, ...props }) => (
    <a {...props} target="_blank" rel="noopener noreferrer" />
  ),
};

interface ChatProps {
  userId?: string;
  sessionId?: string;
  sessionIdRef?: React.MutableRefObject<string | null>;
  s3Uris?: string[];
  onAssistantResponse?: (text: string, charts: ChartBlock[], userMessage?: string) => void;
  savedIncome?: string;
  country?: string;
  currency?: string;
  language?: string;
  currencySymbol?: string;
  paymentBehavior?: string;
  userName?: string;
  t: (key: string) => string;
}

export interface ChatHandle {
  triggerExtraction: (s3Uris: string[], fileNames: string) => void;
  addExternalMessage: (role: 'user' | 'assistant', content: string) => void;
}

export const Chat = forwardRef<ChatHandle, ChatProps>(function Chat(
  { userId = 'demo_user', sessionId, sessionIdRef: externalSessionIdRef, onAssistantResponse, savedIncome, country, currency, language: lang, currencySymbol, paymentBehavior, userName, t },
  ref
) {
  const { messages, isLoading, error, sendMessage, addMessage, sessionIdRef } = useAgent(userId, externalSessionIdRef);
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevMessagesLen = useRef(0);

  useEffect(() => {
    if (sessionId) sessionIdRef.current = sessionId;
  }, [sessionId, sessionIdRef]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  useEffect(() => {
    if (messages.length > prevMessagesLen.current) {
      const newMessages = messages.slice(prevMessagesLen.current);
      for (let i = 0; i < newMessages.length; i++) {
        const msg = newMessages[i];
        if (msg.role === 'assistant' && onAssistantResponse) {
          const parsed = parseResponse(msg.content);
          // Find the preceding user message to detect simulation requests
          const globalIdx = prevMessagesLen.current + i;
          const prevUserMsg = globalIdx > 0 ? messages.slice(0, globalIdx).reverse().find(m => m.role === 'user') : undefined;
          onAssistantResponse(parsed.text, parsed.charts, prevUserMsg?.content);
        }
      }
    }
    prevMessagesLen.current = messages.length;
  }, [messages, onAssistantResponse]);

  useImperativeHandle(ref, () => ({
    triggerExtraction: (uris: string[], fileNames: string) => {
      let prompt = `He subido ${uris.length} estado(s) de cuenta: ${fileNames}. Por favor extrae los datos de estos PDFs.`;
      if (savedIncome) prompt += ` Mi ingreso mensual es S/ ${savedIncome}.`;
      sendMessage(prompt, { pdfs: uris });
    },
    addExternalMessage: (role: 'user' | 'assistant', content: string) => {
      addMessage(role, content);
    },
  }));

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;
    const userInput = input;
    setInput('');
    try {
      const incomeCtx = savedIncome
        ? { ingreso_mensual: `${currencySymbol || 'S/'} ${savedIncome}`, country, currency, language: lang, payment_behavior: paymentBehavior }
        : { country, currency, language: lang, payment_behavior: paymentBehavior };
      await sendMessage(userInput, incomeCtx);
    } catch (err) {
      // Log only error type/message, not full payload which may contain user PII
      console.error('Error al enviar mensaje:', err instanceof Error ? err.message : 'unknown error');
    }
  };

  const locale = lang === 'en' ? 'en-US' : 'es-PE';

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h3>{t('chat_title')}</h3>
        <div className="chat-status">{t('chat_available')}</div>
      </div>

      <div className="messages">
        {messages.length === 0 && (
          <div className="message assistant">
            <div className="message-content">{t('chat_greeting').replace('{name}', userName || '')}</div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const parsed = msg.role === 'assistant' ? parseResponse(msg.content) : null;
          return (
            <div key={idx} className={`message ${msg.role}`}>
              {msg.role === 'assistant' && parsed ? (
                <div className="message-content markdown-body">
                  <Markdown remarkPlugins={MARKDOWN_PLUGINS} components={MARKDOWN_COMPONENTS}>
                    {parsed.text}
                  </Markdown>
                </div>
              ) : (
                <div className="message-content">{msg.content}</div>
              )}
              <div className="message-time">
                {msg.timestamp.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}
              </div>
            </div>
          );
        })}

        {isLoading && (
          <div className="message assistant">
            <div className="message-content thinking">{t('chat_analyzing')}</div>
          </div>
        )}

        {error && (
          <div className="message error">
            <div className="message-content"><Icon name="alert" /> {error}</div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
          placeholder={t('chat_placeholder')}
          disabled={isLoading}
        />
        <button onClick={handleSend} disabled={isLoading || !input.trim()}>
          {isLoading ? '...' : t('chat_send')}
        </button>
      </div>
    </div>
  );
});
