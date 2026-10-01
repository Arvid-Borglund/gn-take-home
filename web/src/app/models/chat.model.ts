// The contract with the agent server (agent/server.py, under /api/chat). The field
// names are snake_case because they come from the Python side unchanged.

/** A ticket that a reply is about. It came out of a tool result, so it exists. */
export interface TicketRef {
  ticket_id: number;
  title: string | null;
  status: string | null;
}

/** One line of the trace above an answer: a tool call or what the tool returned. */
export interface ChatStep {
  kind: 'call' | 'result';
  text: string;
  error: boolean;
}

/** The agent stopped before a delete and asks the user. */
export interface ConfirmQuestion {
  action: string;
  ticket_ids: number[];
}

/** A piece of an answer: plain text, or a ticket number that opens the ticket. */
export interface TextPart {
  text: string;
  ticketId: number | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  steps?: ChatStep[];
  tickets?: TicketRef[];

  // The rest exists only in the browser.
  /** The content split into text and ticket links. */
  parts?: TextPart[];
  /** The reply is still coming in. */
  streaming?: boolean;
  /** The turn failed; shown instead of an answer. */
  error?: string;
  /** Set while the agent waits for a yes or no. */
  confirm?: ConfirmQuestion | null;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  /** A turn crashed in this conversation. It takes no more messages. */
  failed: boolean;
  /** The agent is working on a message in this conversation right now. A turn runs
   *  on the server until it is done, also when the browser that started it is gone. */
  running: boolean;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
  pending_confirmation: ConfirmQuestion | null;
}

export interface ChatHealth {
  status: 'ok' | 'degraded';
  ticket_api: boolean;
  model: string;
}

/**
 * The events of a reply, in the order the server sends them.
 *
 * 'rejected' is the exception: it does not come from the server's stream. ChatService
 * makes it when the server refuses the request itself (for example 409, the agent is
 * still working on the previous message), so that nothing was started.
 */
export type ChatEvent =
  | { event: 'rejected'; data: { message: string } }
  | { event: 'tool_call'; data: ChatStep }
  | { event: 'tool_result'; data: ChatStep }
  | { event: 'answer'; data: { content: string; tickets: TicketRef[] } }
  | { event: 'confirm'; data: ConfirmQuestion }
  | { event: 'error'; data: { message: string } }
  | { event: 'done'; data: {} };
