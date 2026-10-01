import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ChatComponent } from './components/chat/chat.component';
import { TicketViewerComponent } from './components/ticket-viewer/ticket-viewer.component';
import { ChatService } from './services/chat.service';
import { ChatHealth } from './models/chat.model';

/**
 * The page: a top bar, the chat as the main area, and the ticket viewer to the right
 * of it. The viewer takes no room until a ticket is opened.
 */
@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, ChatComponent, TicketViewerComponent],
  template: `
    <header class="topbar">
      <span class="mark"></span>
      <span class="name">Ticket desk</span>
      <span class="tagline">a GenAI agent on the ticketing API</span>
      <span class="health" [title]="healthTitle()">
        <span class="dot" [class.up]="health !== null && health.status === 'ok'"></span>
        {{ health ? health.model : 'agent not reachable' }}
      </span>
    </header>

    <main class="layout">
      <app-chat></app-chat>
      <app-ticket-viewer></app-ticket-viewer>
    </main>
  `,
  styles: [`
    :host { display: flex; flex-direction: column; height: 100vh; }
    .topbar { flex: none; display: flex; align-items: center; gap: 10px; padding: 0 18px; height: 50px; background: var(--teal-dark); color: var(--cream); border-bottom: 3px solid var(--orange); }
    .mark { width: 14px; height: 14px; border-radius: 4px; background: var(--orange); }
    .name { font-size: 16px; font-weight: 700; letter-spacing: .02em; }
    .tagline { font-size: 12px; color: var(--teal-soft); opacity: .75; }
    .health { margin-left: auto; display: flex; align-items: center; gap: 7px; font-size: 12px; font-family: var(--mono); color: var(--teal-soft); }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--grey); }
    .dot.up { background: #6FCF97; }
    .layout { flex: 1; display: flex; min-height: 0; }
  `]
})
export class AppComponent implements OnInit {
  health: ChatHealth | null = null;

  constructor(private chat: ChatService) {}

  ngOnInit(): void {
    this.chat.health().subscribe({
      next: health => (this.health = health),
      error: () => (this.health = null)
    });
  }

  healthTitle(): string {
    if (this.health === null) {
      return 'The agent server does not answer.';
    }
    if (!this.health.ticket_api) {
      return 'The agent is up, but it cannot reach the ticket API.';
    }
    return 'The agent and the ticket API are up.';
  }
}
