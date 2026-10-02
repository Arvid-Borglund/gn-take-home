import { AfterViewChecked, Component, ElementRef, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Observable, Subscription } from 'rxjs';
import { ChatService } from '../../services/chat.service';
import { TicketOpenService } from '../../services/ticket-open.service';
import { ChatEvent, ChatMessage, Conversation, ConversationDetail } from '../../models/chat.model';
import { ChatMessageComponent } from './chat-message.component';
import { ConversationListComponent } from './conversation-list.component';
import { splitIntoParts } from './ticket-links';

/** How often a conversation is read again while a turn is running in it. */
const POLL_INTERVAL_MS = 2000;

/** How often the history is read again while it shows a conversation as working. */
const LIST_POLL_INTERVAL_MS = 3000;

/**
 * The chat: the conversation list to the left, the thread and the input to the right.
 *
 * A turn goes like this. send() adds the user's message and an empty agent message to
 * the thread and opens the stream. apply() fills the agent message in as the events
 * arrive. When the agent asks before a delete, the stream ends with the question
 * pending; answerConfirmation() opens a second stream that continues the same turn.
 *
 * A turn does not belong to the page that started it: the server runs it to the end
 * either way. A page that opens a conversation in the middle of a turn follows it by
 * reading the conversation again every other second (load()).
 */
@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [CommonModule, FormsModule, ChatMessageComponent, ConversationListComponent],
  template: `
    <app-conversation-list
      [conversations]="conversations"
      [currentId]="current ? current.id : null"
      (selected)="select($event)"
      (created)="newConversation()"
      (removed)="remove($event)">
    </app-conversation-list>

    <div class="thread">
      <div #scroller class="messages">
        <div *ngIf="messages.length === 0" class="intro">
          <h2>What should happen to which ticket?</h2>
          <p>
            Ask in plain language. The agent creates, finds, updates and deletes tickets
            through the ticketing API. Ticket numbers in its answers open the ticket next
            to the chat.
          </p>
          <div class="examples-heading">The requests from the assignment</div>
          <div class="examples">
            <button *ngFor="let scenario of scenarios" type="button" (click)="ask(scenario)">{{ scenario }}</button>
          </div>
        </div>

        <app-chat-message *ngFor="let message of messages" [message]="message"
                          (confirmed)="answerConfirmation(message, $event)">
        </app-chat-message>
      </div>

      <div *ngIf="current && current.failed" class="notice">
        This conversation stopped on an error. Start a new one to continue.
      </div>
      <div *ngIf="notice" class="notice">{{ notice }}</div>

      <form class="composer" (ngSubmit)="send()">
        <textarea [(ngModel)]="draft" name="draft" rows="1" autocomplete="off"
                  [placeholder]="waitingForConfirmation ? 'Answer the question above first' : 'Type a request'"
                  (keydown.enter)="onEnter($event)" [disabled]="!canType()"></textarea>
        <button type="submit" [disabled]="!canType() || draft.trim() === ''">Send</button>
      </form>
    </div>
  `,
  styles: [`
    :host { display: flex; flex: 1; min-width: 0; min-height: 0; }
    .thread { flex: 1; display: flex; flex-direction: column; min-width: 0; background: var(--cream); }
    .messages { flex: 1; overflow-y: auto; padding: 20px 24px; display: flex; flex-direction: column; gap: 14px; }

    .intro { max-width: 620px; margin: 6vh auto 0; color: var(--ink); }
    .intro h2 { margin: 0 0 8px; font-size: 22px; color: var(--teal); }
    .intro p { margin: 0 0 18px; font-size: 14px; line-height: 1.5; color: var(--grey); }
    .examples-heading { font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--grey); margin-bottom: 6px; }
    .examples { display: flex; flex-direction: column; gap: 6px; }
    .examples button { text-align: left; background: var(--cream-light); border: 1px solid var(--grey-light); border-left: 3px solid var(--orange); border-radius: 8px; padding: 9px 12px; font-size: 13px; cursor: pointer; color: var(--ink); }
    .examples button:hover { border-color: var(--orange); }

    .notice { margin: 0 24px 8px; padding: 8px 12px; border-radius: 8px; background: #FBE6DA; color: #7A2E06; font-size: 13px; }

    .composer { display: flex; gap: 8px; padding: 14px 24px 18px; border-top: 1px solid var(--grey-light); background: var(--cream-light); }
    .composer textarea { flex: 1; resize: none; border: 1px solid var(--grey-light); border-radius: 10px; padding: 10px 12px; font: inherit; font-size: 14px; background: #fff; color: var(--ink); }
    .composer textarea:focus { outline: 2px solid var(--orange); outline-offset: -1px; }
    .composer button { background: var(--orange); color: #fff; border: 0; border-radius: 10px; padding: 0 20px; font-size: 14px; font-weight: 600; cursor: pointer; }
    .composer button:hover { background: var(--orange-dark); }
    .composer button:disabled { opacity: .45; cursor: default; }
  `]
})
export class ChatComponent implements OnInit, AfterViewChecked, OnDestroy {
  @ViewChild('scroller') scroller?: ElementRef<HTMLDivElement>;

  conversations: Conversation[] = [];
  current: Conversation | null = null;
  messages: ChatMessage[] = [];
  scenarios: string[] = [];
  draft = '';

  /** A reply is coming in. */
  busy = false;
  /** The agent asked before a delete and has not been answered. */
  waitingForConfirmation = false;
  /** Why the server refused the last request. Shown above the input. */
  notice = '';

  private stream?: Subscription;
  private scrollPending = false;

  /** This page is following a turn it did not start, by reading the conversation
   *  again and again (see load()). */
  private watching = false;
  private pollTimer?: ReturnType<typeof setTimeout>;

  /** Set while the history shows a conversation as working (see
   *  followWorkingConversations()). */
  private listTimer?: ReturnType<typeof setTimeout>;

  constructor(private chat: ChatService, private ticketOpen: TicketOpenService) {}

  ngOnInit(): void {
    this.refreshConversations();
    this.refreshScenarios();
  }

  canType(): boolean {
    if (this.busy || this.waitingForConfirmation) {
      return false;
    }
    if (this.current !== null && this.current.failed) {
      return false;
    }
    return true;
  }

  // ----- The conversation list -----

  refreshConversations(): void {
    this.chat.listConversations().subscribe({
      next: list => {
        this.conversations = list;
        // The server may have changed the current conversation (its title, or failed).
        if (this.current !== null) {
          for (const conversation of list) {
            if (conversation.id === this.current.id) {
              this.current = conversation;
            }
          }
        }
        this.followWorkingConversations(list);
      },
      error: () => (this.conversations = [])
    });
  }

  /**
   * While the history marks a conversation as working, the list is read again every
   * few seconds. Otherwise the mark would stay after the turn is over, for a
   * conversation that is not open on this page: nothing else would read the list.
   */
  private followWorkingConversations(list: Conversation[]): void {
    if (this.listTimer !== undefined) {
      clearTimeout(this.listTimer);
      this.listTimer = undefined;
    }

    let anyWorking = false;
    for (const conversation of list) {
      if (conversation.running) {
        anyWorking = true;
      }
    }

    if (anyWorking) {
      this.listTimer = setTimeout(() => this.refreshConversations(), LIST_POLL_INTERVAL_MS);
    }
  }

  refreshScenarios(): void {
    this.chat.scenarios().subscribe({
      next: list => (this.scenarios = list),
      error: () => (this.scenarios = [])
    });
  }

  newConversation(): void {
    this.cancelStream();
    this.current = null;
    this.messages = [];
    this.waitingForConfirmation = false;
    this.notice = '';
    this.refreshScenarios();
  }

  select(conversation: Conversation): void {
    this.cancelStream();
    this.current = conversation;
    this.waitingForConfirmation = false;
    this.notice = '';
    this.load(conversation.id);
  }

  /**
   * Reads the conversation from the server and shows it.
   *
   * A turn runs on the server until it is done, also when the page that started it was
   * closed or reloaded. If the conversation has such a turn going, this page did not
   * get its events, so it reads the conversation again every other second and shows
   * the reply growing, until the server says the turn is over.
   */
  private load(conversationId: number): void {
    this.chat.getConversation(conversationId).subscribe({
      next: detail => {
        // The user has gone to another conversation while this answer was on its way.
        if (this.current === null || this.current.id !== conversationId) {
          return;
        }

        this.show(detail);

        if (detail.running) {
          if (!this.watching) {
            // So that the history marks the conversation as working from now on.
            this.refreshConversations();
          }
          this.watching = true;
          this.busy = true;
          this.pollTimer = setTimeout(() => this.load(conversationId), POLL_INTERVAL_MS);
        } else if (this.watching) {
          // The turn this page was watching is over. So is the reason for a notice
          // that said the agent is still working.
          this.watching = false;
          this.busy = false;
          this.notice = '';
          this.ticketOpen.refresh();
          this.refreshConversations();
          this.refreshScenarios();
        }
      },
      error: () => (this.messages = [])
    });
  }

  private show(detail: ConversationDetail): void {
    this.messages = detail.messages;
    for (const message of this.messages) {
      if (message.role === 'assistant') {
        message.parts = splitIntoParts(message.content, message.tickets || []);
      }
    }

    this.waitingForConfirmation = false;

    if (detail.running) {
      // The dots go on the reply that is being written. Before the agent has saved its
      // first step there is no reply yet, so an empty one is added to carry them.
      let last = this.messages[this.messages.length - 1];
      if (last === undefined || last.role !== 'assistant') {
        last = { role: 'assistant', content: '', steps: [], tickets: [] };
        this.messages.push(last);
      }
      last.streaming = true;
    } else if (detail.pending_confirmation !== null && this.messages.length > 0) {
      // The conversation was left while the agent waited for a yes or no:
      // the question goes back on the reply it belongs to.
      const last = this.messages[this.messages.length - 1];
      last.confirm = detail.pending_confirmation;
      this.waitingForConfirmation = true;
    }

    this.scrollPending = true;
  }

  remove(conversation: Conversation): void {
    this.chat.deleteConversation(conversation.id).subscribe({
      next: () => {
        if (this.current !== null && this.current.id === conversation.id) {
          this.newConversation();
        }
        this.refreshConversations();
      },
      // For example 409: the agent is still working in that conversation.
      error: (error: HttpErrorResponse) => {
        if (error.error && typeof error.error.detail === 'string') {
          this.notice = error.error.detail;
        } else {
          this.notice = 'Could not remove the conversation.';
        }
      }
    });
  }

  // ----- Sending -----

  ask(text: string): void {
    this.draft = text;
    this.send();
  }

  onEnter(event: Event): void {
    // Enter sends, Shift+Enter makes a new line.
    const key = event as KeyboardEvent;
    if (key.shiftKey) {
      return;
    }
    event.preventDefault();
    this.send();
  }

  send(): void {
    const content = this.draft.trim();
    if (content === '' || !this.canType()) {
      return;
    }

    this.draft = '';
    this.notice = '';
    this.busy = true;
    this.messages.push({ role: 'user', content: content });
    const reply: ChatMessage = { role: 'assistant', content: '', steps: [], tickets: [], streaming: true };
    this.messages.push(reply);
    this.scrollPending = true;

    if (this.current !== null) {
      this.listen(this.chat.streamMessage(this.current.id, content), reply, content);
      return;
    }

    // The first message of a new conversation: the conversation is created first.
    this.chat.createConversation().subscribe({
      next: created => {
        this.current = created;
        this.listen(this.chat.streamMessage(created.id, content), reply, content);
      },
      error: () => this.fail(reply, 'Could not create the conversation.')
    });
  }

  answerConfirmation(reply: ChatMessage, confirmed: boolean): void {
    if (this.current === null || this.busy) {
      return;
    }

    reply.confirm = null;
    reply.streaming = true;
    this.waitingForConfirmation = false;
    this.notice = '';
    this.busy = true;
    this.listen(this.chat.streamConfirmation(this.current.id, confirmed), reply, '');
  }

  /** unsentText is what the user typed, to put back in the input if the server
   *  refuses the request. Empty for a confirmation. */
  private listen(events: Observable<ChatEvent>, reply: ChatMessage, unsentText: string): void {
    this.stream = events.subscribe({
      next: event => {
        if (event.event === 'rejected') {
          this.rejected(event.data.message, unsentText);
        } else {
          this.apply(event, reply);
        }
      },
      error: () => this.fail(reply, 'The stream was interrupted.'),
      complete: () => {
        reply.streaming = false;
        this.busy = false;
        this.refreshConversations();
        this.refreshScenarios();
      }
    });
  }

  /**
   * The server refused the request, so nothing was started and the message was not
   * sent. The reason goes above the input, the text goes back into it, and the thread
   * is read again from the server: that removes what send() had already added, and if
   * the reason is that a turn is still running, it starts watching that turn.
   */
  private rejected(message: string, unsentText: string): void {
    this.cancelStream();
    this.notice = message;
    if (unsentText !== '') {
      this.draft = unsentText;
    }
    if (this.current !== null) {
      this.load(this.current.id);
    }
  }

  /** Fills the reply in from one event of the stream. */
  private apply(event: ChatEvent, reply: ChatMessage): void {
    switch (event.event) {
      case 'rejected':
        // Handled in listen(), before a reply exists to fill in.
        break;
      case 'tool_call':
        reply.steps!.push(event.data);
        break;
      case 'tool_result':
        reply.steps!.push(event.data);
        // A tool has run, so an open ticket may have changed.
        this.ticketOpen.refresh();
        break;
      case 'answer':
        reply.content = event.data.content;
        reply.tickets = event.data.tickets;
        reply.parts = splitIntoParts(reply.content, reply.tickets);
        break;
      case 'confirm':
        reply.confirm = event.data;
        this.waitingForConfirmation = true;
        break;
      case 'error':
        reply.error = event.data.message;
        break;
      case 'done':
        break;
    }
    this.scrollPending = true;
  }

  private fail(reply: ChatMessage, message: string): void {
    reply.error = message;
    reply.streaming = false;
    this.busy = false;
  }

  /** Stops listening to the current turn. The turn itself goes on running on the
   *  server; this page just no longer follows it. */
  private cancelStream(): void {
    if (this.stream) {
      this.stream.unsubscribe();
      this.stream = undefined;
    }
    if (this.pollTimer !== undefined) {
      clearTimeout(this.pollTimer);
      this.pollTimer = undefined;
    }
    this.watching = false;
    this.busy = false;
  }

  // ----- Scrolling -----

  ngAfterViewChecked(): void {
    // Runs after Angular has drawn the new messages, so the height is the new height.
    if (this.scrollPending && this.scroller) {
      const element = this.scroller.nativeElement;
      element.scrollTop = element.scrollHeight;
      this.scrollPending = false;
    }
  }

  ngOnDestroy(): void {
    this.cancelStream();
    if (this.listTimer !== undefined) {
      clearTimeout(this.listTimer);
    }
  }
}
