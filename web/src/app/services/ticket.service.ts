import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { TicketDetail, TicketVersion } from '../models/ticket.model';

/**
 * Reads tickets straight from the ticket API, through nginx (/api/tickets/ is passed on
 * to the API's /tickets/). Reading only: there is no method here that changes a ticket,
 * and nginx lets nothing but GET through on this path. Every change goes through the
 * agent.
 */
@Injectable({
  providedIn: 'root'
})
export class TicketService {
  private baseUrl = '/api/tickets';

  constructor(private http: HttpClient) {}

  getTicket(ticketId: number): Observable<TicketDetail> {
    return this.http.get<TicketDetail>(`${this.baseUrl}/${ticketId}`);
  }

  getVersions(ticketId: number): Observable<TicketVersion[]> {
    return this.http.get<TicketVersion[]>(`${this.baseUrl}/${ticketId}/versions`);
  }
}
