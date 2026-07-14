'use server';

import type { InstallmentFormValues } from '@/app/(protected)/installments/installment-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

function toBody(values: InstallmentFormValues) {
  const installmentNum = Number(values.installmentAmount);
  const countNum = Number(values.installmentsCount);
  // Cents math: 5.85 × 3 is 17.549999999999997 in binary floats → the API's
  // decimal_places=2 rejects it with a 422. Rounding the per-installment amount to integer
  // cents first keeps the product exact (count is a validated positive integer).
  const totalAmount = values.hasInterest
    ? Number(values.originalPrice ?? '0')
    : (Math.round(installmentNum * 100) * countNum) / 100;
  return {
    name: values.name,
    total_amount: totalAmount,
    installment_amount: installmentNum,
    installments_count: countNum,
    current_installment: Number(values.currentInstallment),
    currency: values.currency,
    start_date: values.startDate,
    payment_method: values.paymentMethod ?? null,
    credit_card_id: values.paymentMethod === 'credit_card' ? (values.creditCardId ?? null) : null,
  };
}

export async function createInstallment(values: InstallmentFormValues): Promise<void> {
  const res = await authenticatedFetch('/installments', {
    method: 'POST',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to create installment plan');
}

export async function updateInstallment(id: number, values: InstallmentFormValues): Promise<void> {
  const res = await authenticatedFetch(`/installments/${id}`, {
    method: 'PUT',
    body: toBody(values),
  });
  if (!res.ok) throw new Error('Failed to update installment plan');
}

export async function deleteInstallment(id: number): Promise<void> {
  const res = await authenticatedFetch(`/installments/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete installment plan');
}

export async function archiveInstallment(id: number): Promise<void> {
  const res = await authenticatedFetch(`/installments/${id}`, {
    method: 'PUT',
    body: { is_active: false },
  });
  if (!res.ok) throw new Error('Failed to archive installment plan');
}

export async function unarchiveInstallment(id: number): Promise<void> {
  const res = await authenticatedFetch(`/installments/${id}`, {
    method: 'PUT',
    body: { is_active: true },
  });
  if (!res.ok) throw new Error('Failed to unarchive installment plan');
}
