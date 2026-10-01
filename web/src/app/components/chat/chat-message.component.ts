import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatMessage } from '../../models/chat.model';
import { TicketOpenService } from '../../services/ticket-open.service';

/**
 * One message in the thread. An agent message shows, from the top: the steps the agent
 * took (tool calls and tool results), the answer with clickable ticket numbers, the
 * question before a delete, and the tickets the answer is about.
 */
@Component({
  selector: 'app-chat-message',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="msg" [class.msg-user]="message.role === 'user'" [class.msg-assistant]="message.role === 'assistant'">

      <div *ngIf="message.steps && message.steps.length > 0" class="steps">
        <div *ngFor="let step of message.steps" class="step" [class.step-error]="step.error">
          <span class="step-kind">{{ step.kind === 'call' ? 'tool call' : 'tool result' }}</span>
          <span class="step-text">{{ step.text }}</span>
        </div>
      </div>

      <div *ngIf="message.role === 'user'" class="bubble">{{ message.content }}</div>

      <div *ngIf="message.role === 'assistant' && message.parts && message.parts.length > 0" class="bubble">
        <ng-container *ngFor="let part of message.parts">
          <a *ngIf="part.ticketId !== null" class="ticket-link" href="#"
             (click)="open(part.ticketId, $event)" title="Open the ticket">{{ part.text }}</a>
          <ng-container *ngIf="part.ticketId === null">{{ part.text }}</ng-container>
        </ng-container>
      </div>

      <div *ngIf="message.streaming && !message.confirm" class="bubble thinking">
        <span></span><span></span><span></span>
      </div>

      <div *ngIf="message.confirm" class="confirm">
        <div class="confirm-text">
          Delete ticket {{ message.confirm.ticket_ids.join(', ') }} permanently?
          Its comments and history go with it.
        </div>
        <div class="confirm-buttons">
          <button type="button" class="confirm-yes" (click)="confirmed.emit(true)">Delete</button>
          <button type="button" class="confirm-no" (click)="confirmed.emit(false)">Keep it</button>
        </div>
      </div>

      <div *ngIf="message.error" class="bubble error">{{ message.error }}</div>

      <div *ngIf="message.tickets && message.tickets.length > 0" class="tickets">
        <button *ngFor="let ticket of message.tickets" type="button" class="ticket-chip"
                (click)="open(ticket.ticket_id, $event)" title="Open the ticket">
          <span class="chip-id">#{{ ticket.ticket_id }}</span>
          <span *ngIf="ticket.status" class="chip-status" [attr.data-status]="ticket.status">{{ ticket.status }}</span>
          <span *ngIf="ticket.title" class="chip-title">{{ ticket.title }}</span>
        </button>
      </div>
    </div>
  `,
  styles: [`
    .msg { display: flex; flex-direction: column; gap: 6px; max-width: 88%; }
    .msg-user { align-self: flex-end; align-items: flex-end; }
    .msg-assistant { align-self: flex-start; align-items: flex-start; }

    .bubble { padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
    .msg-user .bubble { background: var(--teal); color: var(--cream-light); border-bottom-right-radius: 4px; }
    .msg-assistant .bubble { background: var(--cream-light); color: var(--ink); border: 1px solid var(--grey-light); border-bottom-left-radius: 4px; }
    .bubble.error { background: #FBE6DA; border-color: var(--orange); color: #7A2E06; }

    .ticket-link { color: var(--orange-dark); font-weight: 600; text-decoration: none; border-bottom: 1px dashed var(--orange-dark); }
    .ticket-link:hover { color: var(--teal); border-bottom-color: var(--teal); }

    .steps { display: flex; flex-direction: column; gap: 3px; width: 100%; }
    .step { display: flex; gap: 8px; font-family: var(--mono); font-size: 12px; color: var(--grey); padding-left: 8px; border-left: 2px solid var(--grey-light); }
    .step-kind { flex: none; width: 74px; color: var(--teal-mid); }
    .step-text { word-break: break-word; }
    .step-error { border-left-color: var(--orange); }
    .step-error .step-text { color: var(--orange-dark); }

    .thinking { display: flex; gap: 4px; padding: 14px; }
    .thinking span { width: 6px; height: 6px; border-radius: 50%; background: var(--grey); animation: bounce 1.2s infinite; }
    .thinking span:nth-child(2) { animation-delay: .2s; }
    .thinking span:nth-child(3) { animation-delay: .4s; }
    @keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-4px); } }

    .confirm { background: #FFF4EA; border: 1px solid var(--orange); border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 10px; }
    .confirm-text { font-size: 14px; color: var(--ink); }
    .confirm-buttons { display: flex; gap: 8px; }
    .confirm-buttons button { border-radius: 8px; padding: 7px 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .confirm-yes { background: var(--orange); color: #fff; border: 1px solid var(--orange); }
    .confirm-yes:hover { background: var(--orange-dark); }
    .confirm-no { background: transparent; color: var(--teal); border: 1px solid var(--teal); }
    .confirm-no:hover { background: var(--teal-soft); }

    .tickets { display: flex; flex-wrap: wrap; gap: 6px; }
    .ticket-chip { display: flex; align-items: center; gap: 6px; background: #fff; border: 1px solid var(--grey-light); border-radius: 999px; padding: 4px 12px 4px 10px; cursor: pointer; font-size: 12px; max-width: 320px; }
    .ticket-chip:hover { border-color: var(--orange); }
    .chip-id { color: var(--orange-dark); font-weight: 700; }
    .chip-status { font-size: 10px; font-weight: 700; letter-spacing: .04em; padding: 1px 6px; border-radius: 4px; color: #fff; background: var(--grey); }
    .chip-status[data-status="OPEN"] { background: var(--orange); }
    .chip-status[data-status="RESOLVED"] { background: var(--teal-mid); }
    .chip-title { color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  `]
})
export class ChatMessageComponent {
  @Input({ required: true }) message!: ChatMessage;

  /** The user's answer to the question before a delete: true for yes. */
  @Output() confirmed = new EventEmitter<boolean>();

  constructor(private ticketOpen: TicketOpenService) {}

  open(ticketId: number, event: Event): void {
    event.preventDefault();
    this.ticketOpen.open(ticketId);
  }
}
