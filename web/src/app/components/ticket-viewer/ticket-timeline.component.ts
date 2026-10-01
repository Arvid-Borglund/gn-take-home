import { Component, EventEmitter, Input, OnChanges, Output, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TicketComment, TicketSnapshot, TicketVersion } from '../../models/ticket.model';

/** A comment placed on the timeline. */
interface Pin {
  comment: TicketComment;
  /** Where in its section the pin sits, in percent from the left. */
  position: number;
}

/** One version of the ticket: the stretch of time from that change to the next. */
interface Section {
  version: TicketVersion;
  /** What that version changed, compared with the one before it. */
  changes: string[];
  pins: Pin[];
}

/**
 * The version history of a ticket as a timeline. Every version is a section, coloured
 * by the status the ticket had during it. A click on a section shows the ticket as it
 * was in that version. The pins are the comments, each one in the section of the
 * version it was written on, placed by its time.
 */
@Component({
  selector: 'app-ticket-timeline',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="track">
      <div *ngFor="let section of sections" class="section"
           [class.selected]="section.version.versionNo === selectedVersionNo"
           [attr.data-status]="section.version.snapshot.status"
           (click)="versionSelected.emit(section.version.versionNo)"
           title="Show the ticket as it was in this version">

        <div class="pins">
          <button *ngFor="let pin of section.pins" type="button" class="pin"
                  [class.active]="pin.comment === selectedComment"
                  [style.left.%]="pin.position"
                  [title]="'Comment, ' + (pin.comment.timeOfComment | date:'d MMM HH:mm:ss')"
                  (click)="selectComment(pin.comment, $event)">
          </button>
        </div>

        <div class="bar"></div>

        <div class="label">
          <span class="version-no">Version {{ section.version.versionNo }}</span>
          <span class="status">{{ section.version.snapshot.status }}</span>
        </div>
        <div class="time">{{ section.version.timeOfVersion | date:'d MMM y, HH:mm:ss' }}</div>
        <div class="changes">
          <div *ngFor="let change of section.changes">{{ change }}</div>
        </div>
      </div>
    </div>

    <div class="legend">
      <span class="legend-pin"></span> a comment, placed at the time it was written
    </div>

    <div *ngIf="selectedComment" class="comment">
      <div class="comment-meta">
        Comment on version {{ selectedComment.versionNo }},
        {{ selectedComment.timeOfComment | date:'d MMM y, HH:mm:ss' }}
      </div>
      <div class="comment-body">{{ selectedComment.body }}</div>
    </div>
  `,
  styles: [`
    :host { display: block; background: #fff; border: 1px solid var(--grey-light); border-radius: 10px; padding: 14px 14px 10px; }

    .track { display: flex; overflow-x: auto; padding-bottom: 6px; }
    .section { flex: 1 1 0; min-width: 118px; padding: 0 8px 8px 0; cursor: pointer; border-radius: 6px; }
    .section:hover .bar { filter: brightness(1.1); }

    /* The pins stand on top of the bar. */
    .pins { position: relative; height: 26px; }
    .pin { position: absolute; bottom: 2px; width: 16px; height: 16px; margin-left: -8px; padding: 0; border: 2px solid var(--ink); border-radius: 50% 50% 50% 0; transform: rotate(-45deg); background: var(--cream-light); cursor: pointer; }
    .pin:hover, .pin.active { background: var(--ink); }

    /* The bar is the version: coloured by status, with a dot where the change happened. */
    .bar { position: relative; height: 10px; border-radius: 5px; background: var(--grey); }
    .bar::before { content: ''; position: absolute; left: -2px; top: -4px; width: 14px; height: 14px; border-radius: 50%; background: inherit; border: 3px solid #fff; box-shadow: 0 0 0 1px var(--grey-light); }
    .section[data-status="OPEN"] .bar { background: var(--orange); }
    .section[data-status="RESOLVED"] .bar { background: var(--teal-mid); }
    .section[data-status="CLOSED"] .bar { background: var(--grey); }
    .section.selected .bar { height: 14px; margin-top: -2px; margin-bottom: -2px; box-shadow: 0 0 0 2px var(--ink); }

    .label { display: flex; align-items: baseline; gap: 6px; margin-top: 10px; }
    .version-no { font-size: 13px; font-weight: 700; color: var(--ink); }
    .section.selected .version-no { color: var(--orange-dark); }
    .status { font-size: 10px; font-weight: 700; letter-spacing: .04em; color: var(--grey); }
    .time { font-size: 11px; color: var(--grey); }
    .changes { margin-top: 4px; font-size: 12px; color: var(--ink); line-height: 1.4; }

    .legend { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 11px; color: var(--grey); }
    .legend-pin { width: 9px; height: 9px; border: 2px solid var(--ink); border-radius: 50% 50% 50% 0; transform: rotate(-45deg); }

    .comment { margin-top: 10px; padding: 10px 12px; border-left: 3px solid var(--ink); background: var(--cream); border-radius: 0 8px 8px 0; }
    .comment-meta { font-size: 11px; color: var(--grey); margin-bottom: 4px; }
    .comment-body { font-size: 13px; color: var(--ink); white-space: pre-wrap; }
  `]
})
export class TicketTimelineComponent implements OnChanges {
  @Input() versions: TicketVersion[] = [];
  @Input() comments: TicketComment[] = [];
  @Input() selectedVersionNo: number | null = null;

  @Output() versionSelected = new EventEmitter<number>();

  sections: Section[] = [];
  selectedComment: TicketComment | null = null;

  /** Runs when an input changes. Picking another version changes nothing in the
   *  timeline itself, so the sections are only rebuilt for new versions or comments. */
  ngOnChanges(changes: SimpleChanges): void {
    if (!changes['versions'] && !changes['comments']) {
      return;
    }

    this.sections = this.buildSections();

    // Keep the open comment open across a reload, if it is still there.
    if (this.selectedComment !== null) {
      const openId = this.selectedComment.commentId;
      this.selectedComment = null;
      for (const comment of this.comments) {
        if (comment.commentId === openId) {
          this.selectedComment = comment;
        }
      }
    }
  }

  selectComment(comment: TicketComment, event: Event): void {
    // Without this the click would also select the section under the pin.
    event.stopPropagation();

    if (this.selectedComment === comment) {
      this.selectedComment = null;
    } else {
      this.selectedComment = comment;
    }
  }

  private buildSections(): Section[] {
    const sections: Section[] = [];

    for (let index = 0; index < this.versions.length; index++) {
      const version = this.versions[index];

      let previous: TicketSnapshot | null = null;
      if (index > 0) {
        previous = this.versions[index - 1].snapshot;
      }

      // A section lasts from its own change to the next one. The last section is
      // still going on, so it lasts until now.
      const start = new Date(version.timeOfVersion).getTime();
      let end = Date.now();
      if (index < this.versions.length - 1) {
        end = new Date(this.versions[index + 1].timeOfVersion).getTime();
      }

      const pins: Pin[] = [];
      for (const comment of this.comments) {
        if (comment.versionNo === version.versionNo) {
          const time = new Date(comment.timeOfComment).getTime();
          pins.push({ comment: comment, position: this.positionOf(time, start, end) });
        }
      }

      sections.push({
        version: version,
        changes: this.describeChanges(previous, version.snapshot),
        pins: pins
      });
    }

    return sections;
  }

  /** How far into its section a moment is, in percent, kept away from the edges. */
  private positionOf(time: number, start: number, end: number): number {
    if (end <= start) {
      return 50;
    }

    let position = ((time - start) / (end - start)) * 100;
    if (position < 8) {
      position = 8;
    }
    if (position > 94) {
      position = 94;
    }
    return position;
  }

  private describeChanges(previous: TicketSnapshot | null, current: TicketSnapshot): string[] {
    if (previous === null) {
      return ['Ticket created'];
    }

    const changes: string[] = [];

    if (previous.status !== current.status) {
      changes.push(`Status ${previous.status} to ${current.status}`);
    }
    if (previous.title !== current.title) {
      changes.push('Title changed');
    }
    if (previous.description !== current.description) {
      changes.push('Description changed');
    }
    if (previous.resolution !== current.resolution) {
      if (previous.resolution === null) {
        changes.push('Resolution added');
      } else {
        changes.push('Resolution changed');
      }
    }

    return changes;
  }
}
