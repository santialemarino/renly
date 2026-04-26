// Tolerance (in display-currency units) for treating an installment plan as
// having interest. `installment × count` minus `total_amount` greater than this
// epsilon means the plan is With interest; anything within is float dust.
export const INTEREST_EPSILON = 0.01;
