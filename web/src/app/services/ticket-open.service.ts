import { Injectable } from '@angular/core';
import { Observable, Subject } from 'rxjs';

/**
 * The bridge between the chat and the ticket viewer. The chat says "open ticket 4" or
 * "the agent just changed something", and the viewer reacts. Neither of them has to
 * know about the other.
 */
@Injectable({
  providedIn: 'root'
})
export class TicketOpenService {
  private openRequests = new Subject<number>();
  private refreshRequests = new Subject<void>();

  readonly open$: Observable<number> = this.openRequests.asObservable();
  readonly refresh$: Observable<void> = this.refreshRequests.asObservable();

  open(ticketId: number): void {
    this.openRequests.next(ticketId);
  }

  /** Called after every tool result: the open tickets may have changed. */
  refresh(): void {
    this.refreshRequests.next();
  }
}
