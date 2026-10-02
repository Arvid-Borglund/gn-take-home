import { Component, OnDestroy, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Subscription } from 'rxjs';
import { TicketService } from '../../services/ticket.service';
import { TicketOpenService } from '../../services/ticket-open.service';
import { TicketSnapshot, TicketTab, TicketVersion } from '../../models/ticket.model';
import { TicketTimelineComponent } from './ticket-timeline.component';

/**
 * The ticket viewer next to the chat: one tab per open ticket. It only reads. There is
 * no edit button on purpose: every change to a ticket goes through the agent.
 *
 * A tab shows the current state of its ticket, or, when a version is picked in the
 * timeline, the ticket as it was in that version.
 */
@Component({
  selector: 'app-ticket-viewer',
  standalone: true,
  imports: [CommonModule, TicketTimelineComponent],
  template: `
    <aside *ngIf="tabs.length > 0" class="viewer">
      <div class="tabs">
        <div *ngFor="let tab of tabs" class="tab" [class.active]="tab.ticketId === activeId"
             (click)="activeId = tab.ticketId">
          <span class="tab-id">#{{ tab.ticketId }}</span>
          <span class="tab-title">{{ tab.detail ? tab.detail.ticket.title : '' }}</span>
          <button type="button" class="tab-close" title="Close the tab" (click)="close(tab, $event)">×</button>
        </div>
      </div>

      <div *ngIf="activeTab() as tab" class="content">
        <div *ngIf="tab.error" class="missing">{{ tab.error }}</div>

        <ng-container *ngIf="tab.detail as detail">
          <div class="head">
            <span class="ticket-id">Ticket #{{ detail.ticket.ticketId }}</span>
            <span class="status" [attr.data-status]="shown(tab).status">{{ shown(tab).status }}</span>
          </div>
          <h2>{{ shown(tab).title }}</h2>

          <div *ngIf="isOldVersion(tab)" class="old-version">
            <span>
              This is version {{ tab.selectedVersionNo }} of {{ detail.ticket.versionNo }},
              not the ticket as it is now.
            </span>
            <button type="button" (click)="tab.selectedVersionNo = null">Back to the current version</button>
          </div>

          <h3>Description</h3>
          <p class="text">{{ shown(tab).description }}</p>

          <h3>Resolution</h3>
          <p *ngIf="shown(tab).resolution" class="text">{{ shown(tab).resolution }}</p>
          <p *ngIf="!shown(tab).resolution" class="text none">No resolution note.</p>

          <div class="meta">
            <div><span>Created</span>{{ detail.ticket.created | date:'d MMM y, HH:mm' }}</div>
            <div><span>Last changed</span>{{ detail.ticket.updated | date:'d MMM y, HH:mm' }}</div>
            <div><span>Versions</span>{{ detail.ticket.versionNo }}</div>
          </div>

          <button type="button" class="history-button" [class.open]="tab.historyOpen" (click)="toggleHistory(tab)">
            {{ tab.historyOpen ? 'Hide version history' : 'Version history' }}
          </button>

          <app-ticket-timeline *ngIf="tab.historyOpen && tab.versions.length > 0"
            [versions]="tab.versions"
            [comments]="detail.comments"
            [selectedVersionNo]="tab.selectedVersionNo === null ? detail.ticket.versionNo : tab.selectedVersionNo"
            (versionSelected)="selectVersion(tab, $event)">
          </app-ticket-timeline>

          <h3>Comments ({{ detail.comments.length }})</h3>
          <p *ngIf="detail.comments.length === 0" class="text none">No comments.</p>
          <div *ngFor="let comment of detail.comments" class="comment">
            <div class="comment-meta">
              {{ comment.timeOfComment | date:'d MMM y, HH:mm' }} · written on version {{ comment.versionNo }}
            </div>
            <div class="comment-body">{{ comment.body }}</div>
          </div>

          <div class="read-only">Read-only. Ask the agent in the chat to change this ticket.</div>
        </ng-container>
      </div>
    </aside>
  `,
  styles: [`
    :host { display: flex; min-height: 0; }
    .viewer { width: 44vw; min-width: 420px; max-width: 760px; display: flex; flex-direction: column; background: var(--cream-light); border-left: 1px solid var(--grey-light); }

    .tabs { display: flex; flex: none; overflow-x: auto; background: var(--teal-soft); border-bottom: 1px solid var(--grey-light); }
    /* The tabs share the width: a tab is as wide as its title, at most 220px, and gets
       narrower when there are many, down to 84px. Only the title gives way; the ticket
       number and the x stay. With more tabs than fit at 84px the row scrolls. */
    .tab { display: flex; align-items: center; gap: 6px; padding: 9px 8px 9px 12px; border-top: 3px solid transparent; border-right: 1px solid var(--grey-light); cursor: pointer; font-size: 13px; flex: 0 1 auto; min-width: 84px; max-width: 220px; }
    .tab.active { background: var(--cream-light); border-top-color: var(--orange); }
    .tab-id { flex: none; font-weight: 700; color: var(--orange-dark); }
    .tab-title { flex: 1 1 auto; min-width: 0; color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .tab-close { flex: none; background: transparent; border: 0; font-size: 16px; line-height: 1; color: var(--grey); cursor: pointer; padding: 0 4px; }
    .tab-close:hover { color: var(--ink); }

    .content { flex: 1; overflow-y: auto; padding: 20px 24px 28px; }
    .missing { padding: 12px 14px; border-radius: 8px; background: #FBE6DA; color: #7A2E06; font-size: 14px; }

    .head { display: flex; align-items: center; gap: 10px; }
    .ticket-id { font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; color: var(--grey); }
    .status { font-size: 11px; font-weight: 700; letter-spacing: .04em; padding: 2px 8px; border-radius: 4px; color: #fff; background: var(--grey); }
    .status[data-status="OPEN"] { background: var(--orange); }
    .status[data-status="RESOLVED"] { background: var(--teal-mid); }
    h2 { margin: 6px 0 14px; font-size: 21px; color: var(--teal); }
    h3 { margin: 18px 0 4px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--grey); }
    .text { margin: 0; font-size: 14px; line-height: 1.5; color: var(--ink); white-space: pre-wrap; }
    .text.none { color: var(--grey); font-style: italic; }

    .old-version { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 6px; padding: 8px 12px; border-radius: 8px; background: #FFF4EA; border: 1px solid var(--orange); font-size: 13px; color: var(--ink); }
    .old-version button { flex: none; background: transparent; border: 1px solid var(--teal); color: var(--teal); border-radius: 6px; padding: 4px 10px; font-size: 12px; cursor: pointer; }
    .old-version button:hover { background: var(--teal-soft); }

    .meta { display: flex; gap: 28px; margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--grey-light); font-size: 13px; color: var(--ink); }
    .meta span { display: block; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--grey); }

    .history-button { margin: 18px 0 10px; background: var(--teal); color: var(--cream-light); border: 0; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .history-button:hover { background: var(--teal-mid); }
    .history-button.open { background: transparent; color: var(--teal); box-shadow: inset 0 0 0 1px var(--teal); }

    .comment { margin-top: 8px; padding: 9px 12px; background: #fff; border: 1px solid var(--grey-light); border-radius: 8px; }
    .comment-meta { font-size: 11px; color: var(--grey); margin-bottom: 3px; }
    .comment-body { font-size: 13px; color: var(--ink); white-space: pre-wrap; }

    .read-only { margin-top: 24px; font-size: 12px; color: var(--grey); }
  `]
})
export class TicketViewerComponent implements OnInit, OnDestroy {
  tabs: TicketTab[] = [];
  activeId: number | null = null;

  private subscriptions: Subscription[] = [];

  constructor(private tickets: TicketService, private ticketOpen: TicketOpenService) {}

  ngOnInit(): void {
    this.subscriptions.push(this.ticketOpen.open$.subscribe(ticketId => this.open(ticketId)));
    this.subscriptions.push(this.ticketOpen.refresh$.subscribe(() => this.reloadAll()));
  }

  ngOnDestroy(): void {
    for (const subscription of this.subscriptions) {
      subscription.unsubscribe();
    }
  }

  // ----- Tabs -----

  open(ticketId: number): void {
    // A ticket that is already open is brought to the front, not opened twice.
    for (const tab of this.tabs) {
      if (tab.ticketId === ticketId) {
        this.activeId = ticketId;
        this.load(tab);
        return;
      }
    }

    const tab: TicketTab = {
      ticketId: ticketId,
      detail: null,
      error: '',
      historyOpen: false,
      versions: [],
      selectedVersionNo: null
    };
    this.tabs.push(tab);
    this.activeId = ticketId;
    this.load(tab);
  }

  close(tab: TicketTab, event: Event): void {
    // Without this the click would also activate the tab it closes.
    event.stopPropagation();

    const index = this.tabs.indexOf(tab);
    this.tabs.splice(index, 1);

    if (this.activeId === tab.ticketId) {
      this.activeId = null;
      if (this.tabs.length > 0) {
        // The neighbour takes over: the tab that moved into the closed one's place,
        // or the last one when the closed tab was the last.
        const next = Math.min(index, this.tabs.length - 1);
        this.activeId = this.tabs[next].ticketId;
      }
    }
  }

  activeTab(): TicketTab | null {
    for (const tab of this.tabs) {
      if (tab.ticketId === this.activeId) {
        return tab;
      }
    }
    return null;
  }

  // ----- Loading -----

  /** The agent has run a tool: every open ticket is read again. */
  reloadAll(): void {
    for (const tab of this.tabs) {
      this.load(tab);
    }
  }

  private load(tab: TicketTab): void {
    this.tickets.getTicket(tab.ticketId).subscribe({
      next: detail => {
        tab.detail = detail;
        tab.error = '';
        if (tab.historyOpen) {
          this.loadVersions(tab);
        }
      },
      error: (error: HttpErrorResponse) => {
        // For example a ticket the agent has just deleted. The API answers 404 with
        // "Ticket 4 does not exist." in detail, and that is what is shown.
        tab.detail = null;
        tab.versions = [];
        tab.selectedVersionNo = null;
        tab.error = this.errorText(error, tab.ticketId);
      }
    });
  }

  private loadVersions(tab: TicketTab): void {
    this.tickets.getVersions(tab.ticketId).subscribe({
      next: versions => (tab.versions = versions),
      error: () => (tab.versions = [])
    });
  }

  private errorText(error: HttpErrorResponse, ticketId: number): string {
    if (error.error && typeof error.error.detail === 'string') {
      return error.error.detail;
    }
    return `Ticket ${ticketId} could not be loaded.`;
  }

  // ----- Version history -----

  toggleHistory(tab: TicketTab): void {
    tab.historyOpen = !tab.historyOpen;

    if (tab.historyOpen) {
      this.loadVersions(tab);
    } else {
      // Closing the history goes back to the ticket as it is now.
      tab.selectedVersionNo = null;
    }
  }

  selectVersion(tab: TicketTab, versionNo: number): void {
    tab.selectedVersionNo = versionNo;
  }

  isOldVersion(tab: TicketTab): boolean {
    if (tab.detail === null || tab.selectedVersionNo === null) {
      return false;
    }
    return tab.selectedVersionNo !== tab.detail.ticket.versionNo;
  }

  /** The fields to show: those of the picked version, or else the current ones. */
  shown(tab: TicketTab): TicketSnapshot {
    if (tab.selectedVersionNo !== null) {
      const version = this.findVersion(tab.versions, tab.selectedVersionNo);
      if (version !== null) {
        return version.snapshot;
      }
    }

    // tab.detail is set whenever this is called: the template only shows the fields
    // inside *ngIf="tab.detail".
    return tab.detail!.ticket;
  }

  private findVersion(versions: TicketVersion[], versionNo: number): TicketVersion | null {
    for (const version of versions) {
      if (version.versionNo === versionNo) {
        return version;
      }
    }
    return null;
  }
}
