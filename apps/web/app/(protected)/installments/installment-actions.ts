'use server';

import type { InstallmentFormValues } from '@/app/(protected)/installments/installment-form-schema';
import { authenticatedFetch } from '@/lib/authenticated-fetch';

function toBody(values: InstallmentFormValues) {
  const {
    totalAmount,
    installmentAmount,
    installmentsCount,
    currentInstallment,
    startDate,
    paymentMethod,
    creditCardId,
    ...rest
  } = values;
  return {
    ...rest,
    total_amount: Number(totalAmount),
    installment_amount: Number(installmentAmount),
    installments_count: Number(installmentsCount),
    current_installment: Number(currentInstallment),
    start_date: startDate,
    payment_method: paymentMethod ?? null,
    credit_card_id: paymentMethod === 'credit_card' ? (creditCardId ?? null) : null,
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
