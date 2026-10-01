import { TextPart, TicketRef } from '../../models/chat.model';

/**
 * Splits an answer into plain text and ticket links.
 *
 * "#4" and "ticket 4" become links, but only when ticket 4 is among the tickets the
 * reply is about. Those come from the agent's tool calls and their results (see
 * agent/transcript.py), never from the model's text. Any other number stays plain
 * text: it is the user's own, a ticket that does not exist, or something the model
 * made up.
 *
 * The parts are shown with Angular's normal text binding, so nothing the model writes
 * is ever treated as HTML.
 */

// "#4", "ticket 4", "ticket #4", "ticket id 4", in any letter case.
const TICKET_MENTION = /(#|\bticket\s+(?:id\s+)?#?)(\d+)/gi;

export function splitIntoParts(text: string, tickets: TicketRef[]): TextPart[] {
  const knownIds: number[] = [];
  for (const ticket of tickets) {
    knownIds.push(ticket.ticket_id);
  }

  const parts: TextPart[] = [];
  let plainStart = 0;

  // exec() with the g flag finds the next mention on each call, and null after the last.
  TICKET_MENTION.lastIndex = 0;
  let match = TICKET_MENTION.exec(text);

  while (match !== null) {
    const ticketId = Number(match[2]);

    if (knownIds.includes(ticketId)) {
      if (match.index > plainStart) {
        parts.push({ text: text.slice(plainStart, match.index), ticketId: null });
      }
      parts.push({ text: match[0], ticketId: ticketId });
      plainStart = match.index + match[0].length;
    }

    match = TICKET_MENTION.exec(text);
  }

  if (plainStart < text.length) {
    parts.push({ text: text.slice(plainStart), ticketId: null });
  }

  return parts;
}
