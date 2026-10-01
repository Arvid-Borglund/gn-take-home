import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { ChatEvent, ChatHealth, Conversation, ConversationDetail } from '../models/chat.model';

/**
 * Parses one server-sent event ("event: x\ndata: {...}") into a ChatEvent.
 * Returns null for a block without data.
 */
export function parseSseBlock(block: string): ChatEvent | null {
  let event = 'message';
  let data = '';

  for (const line of block.split('\n')) {
    if (line.startsWith('event: ')) {
      event = line.slice('event: '.length);
    } else if (line.startsWith('data: ')) {
      data += line.slice('data: '.length);
    }
  }

  if (data === '') {
    return null;
  }

  try {
    return { event: event, data: JSON.parse(data) } as ChatEvent;
  } catch {
    return { event: 'error', data: { message: 'Could not read the answer from the agent.' } };
  }
}

@Injectable({
  providedIn: 'root'
})
export class ChatService {
  private baseUrl = '/api/chat';

  constructor(private http: HttpClient) {}

  health(): Observable<ChatHealth> {
    return this.http.get<ChatHealth>(`${this.baseUrl}/health`);
  }

  /** The requests from the assignment, with real ticket ids filled in. */
  scenarios(): Observable<string[]> {
    return this.http.get<string[]>(`${this.baseUrl}/scenarios`);
  }

  listConversations(): Observable<Conversation[]> {
    return this.http.get<Conversation[]>(`${this.baseUrl}/conversations`);
  }

  createConversation(): Observable<Conversation> {
    return this.http.post<Conversation>(`${this.baseUrl}/conversations`, {});
  }

  getConversation(id: number): Observable<ConversationDetail> {
    return this.http.get<ConversationDetail>(`${this.baseUrl}/conversations/${id}`);
  }

  deleteConversation(id: number): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/conversations/${id}`);
  }

  /** Sends a message. The reply comes back as a stream of events. */
  streamMessage(conversationId: number, content: string): Observable<ChatEvent> {
    const url = `${this.baseUrl}/conversations/${conversationId}/messages`;
    return this.stream(url, { content: content });
  }

  /** Answers the agent's question before a delete. The turn continues as a stream. */
  streamConfirmation(conversationId: number, confirmed: boolean): Observable<ChatEvent> {
    const url = `${this.baseUrl}/conversations/${conversationId}/confirmation`;
    return this.stream(url, { confirmed: confirmed });
  }

  /**
   * POSTs the body and reads the answer as server-sent events. HttpClient cannot read a
   * streamed answer to a POST, so this uses fetch and a reader on response.body.
   * Unsubscribing cancels the request.
   */
  private stream(url: string, body: object): Observable<ChatEvent> {
    return new Observable<ChatEvent>(subscriber => {
      const controller = new AbortController();

      const read = async () => {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
          body: JSON.stringify(body),
          signal: controller.signal
        });

        // The server refused the request, so no turn was started: not an event of a
        // reply, but an answer about the request itself.
        if (!response.ok || response.body === null) {
          subscriber.next({ event: 'rejected', data: { message: await this.errorText(response) } });
          return;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // The bytes arrive in chunks that can end anywhere. An event is complete when
        // the buffer holds the empty line that ends it.
        while (true) {
          const chunk = await reader.read();
          if (chunk.done) {
            break;
          }
          buffer += decoder.decode(chunk.value, { stream: true });

          let end = buffer.indexOf('\n\n');
          while (end >= 0) {
            const parsed = parseSseBlock(buffer.slice(0, end));
            buffer = buffer.slice(end + 2);
            if (parsed !== null) {
              subscriber.next(parsed);
            }
            end = buffer.indexOf('\n\n');
          }
        }
      };

      read()
        .catch(error => {
          if (!controller.signal.aborted) {
            subscriber.next({ event: 'error', data: { message: `Could not reach the agent: ${error}` } });
          }
        })
        .finally(() => subscriber.complete());

      return () => controller.abort();
    });
  }

  /** The server answers an error as {"detail": "..."}. */
  private async errorText(response: Response): Promise<string> {
    try {
      const problem = await response.json();
      if (typeof problem.detail === 'string') {
        return problem.detail;
      }
    } catch {
      // Not JSON: fall through to the status line.
    }
    return `The agent answered ${response.status} ${response.statusText}`.trim();
  }
}
