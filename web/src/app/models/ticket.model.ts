// What the ticket API (api/, ASP.NET Core) returns. The field names are camelCase
// because that is how the API writes its JSON.

export interface Ticket {
  ticketId: number;
  title: string;
  description: string;
  status: string;
  resolution: string | null;
  created: string;
  updated: string;
  versionNo: number;
}

export interface TicketComment {
  commentId: number;
  /** The version the ticket had when the comment was written. */
  versionNo: number;
  body: string;
  timeOfComment: string;
}

/** GET /tickets/{id} */
export interface TicketDetail {
  ticket: Ticket;
  comments: TicketComment[];
}

/** The ticket's fields as they were in one version. Comes straight from the jsonb
 *  column in the database, so these names are the column names. */
export interface TicketSnapshot {
  title: string;
  description: string;
  status: string;
  resolution: string | null;
}

/** One item of GET /tickets/{id}/versions */
export interface TicketVersion {
  versionNo: number;
  timeOfVersion: string;
  snapshot: TicketSnapshot;
}

/** One open ticket in the viewer. */
export interface TicketTab {
  ticketId: number;
  detail: TicketDetail | null;
  /** Set when the ticket could not be loaded, in the API's own words. */
  error: string;
  historyOpen: boolean;
  /** Loaded the first time the history is opened. */
  versions: TicketVersion[];
  /** The version being looked at. null means the current state of the ticket. */
  selectedVersionNo: number | null;
}
