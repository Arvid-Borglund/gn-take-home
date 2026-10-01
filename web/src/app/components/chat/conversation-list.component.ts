import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Conversation } from '../../models/chat.model';

/** The chat history: the list of conversations to the left of the thread. */
@Component({
  selector: 'app-conversation-list',
  standalone: true,
  imports: [CommonModule],
  template: `
    <button type="button" class="new" (click)="created.emit()">+ New conversation</button>

    <div class="heading">History</div>
    <div *ngIf="conversations.length === 0" class="empty">No conversations yet.</div>

    <div *ngFor="let conversation of conversations" class="conv"
         [class.active]="conversation.id === currentId" (click)="selected.emit(conversation)">
      <span class="conv-title">{{ conversation.title || 'New conversation' }}</span>
      <span class="conv-meta">
        {{ conversation.updated_at | date:'d MMM HH:mm' }}
        <ng-container *ngIf="conversation.failed"> · stopped on an error</ng-container>
        <ng-container *ngIf="conversation.running"> · working</ng-container>
      </span>
      <button type="button" class="conv-delete" title="Remove the conversation"
              (click)="remove(conversation, $event)">×</button>
    </div>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; gap: 4px; width: 250px; flex: none; background: var(--teal); color: var(--cream); padding: 12px; overflow-y: auto; }
    .new { background: var(--orange); color: #fff; border: 0; border-radius: 8px; padding: 9px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .new:hover { background: var(--orange-dark); }
    .heading { font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--teal-soft); opacity: .7; margin: 14px 4px 4px; }
    .empty { font-size: 12px; color: var(--teal-soft); padding: 4px; }
    .conv { position: relative; display: flex; flex-direction: column; gap: 2px; border-left: 3px solid transparent; border-radius: 6px; padding: 8px 26px 8px 9px; cursor: pointer; }
    .conv:hover { background: var(--teal-mid); }
    .conv.active { background: var(--teal-mid); border-left-color: var(--orange); }
    .conv-title { font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .conv-meta { font-size: 11px; color: var(--teal-soft); opacity: .8; }
    .conv-delete { position: absolute; right: 4px; top: 6px; background: transparent; border: 0; color: var(--cream); font-size: 16px; cursor: pointer; opacity: 0; }
    .conv:hover .conv-delete { opacity: .8; }
  `]
})
export class ConversationListComponent {
  @Input() conversations: Conversation[] = [];
  @Input() currentId: number | null = null;

  @Output() selected = new EventEmitter<Conversation>();
  @Output() created = new EventEmitter<void>();
  @Output() removed = new EventEmitter<Conversation>();

  remove(conversation: Conversation, event: Event): void {
    // Without this the click would also select the conversation it removes.
    event.stopPropagation();
    this.removed.emit(conversation);
  }
}
