// Cross-entity API contract types shared by the lib/api feature modules.

export type SortOrder = 'asc' | 'desc';

// Thrown when the API denies admin access (403). Admin pages map this to a 404 (notFound) so the
// page's existence stays hidden from non-admins (not a 403). Shared by every admin-only feature.
export class AdminForbiddenError extends Error {
  constructor() {
    super('admin_forbidden');
    this.name = 'AdminForbiddenError';
  }
}
