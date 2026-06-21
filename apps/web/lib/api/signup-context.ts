import 'server-only';

import { cache } from 'react';

import { getSignupContext as fetchSignupContext, type SignupContext } from '@/lib/auth-api';

// Server-side, request-memoized signup context (mode + invited email). Memoized so callers that both
// read the mode in one render — the landing page and the public header — share a single API call.
export const getSignupContext = cache(
  (inviteToken?: string): Promise<SignupContext> => fetchSignupContext(inviteToken),
);
