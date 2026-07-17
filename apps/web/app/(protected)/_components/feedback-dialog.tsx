'use client';

import { useMemo } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from '@repo/ui/components';
import { submitFeedback } from '@/app/(protected)/_components/feedback-actions';
import {
  feedbackFormSchema,
  type FeedbackFormData,
} from '@/app/(protected)/_components/feedback-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import { FEEDBACK_CATEGORIES, MAX_FEEDBACK_LENGTH } from '@/lib/constants/feedback';

interface FeedbackDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// The in-app feedback form (SHELL-7): pick a category, write a message. The caller's account email
// is attached server-side, so the form asks for neither. Reachable from the sidebar.
export function FeedbackDialog({ open, onOpenChange }: FeedbackDialogProps) {
  const t = useTranslations('feedback');
  const tCommon = useTranslations('common');

  const schema = useMemo(() => feedbackFormSchema(tCommon), [tCommon]);

  const form = useForm<FeedbackFormData>({
    resolver: zodResolver(schema),
    defaultValues: { category: undefined, message: '' },
  });

  // Submits the feedback; on success toasts, closes, and resets so the next open starts clean.
  async function onSubmit(values: FeedbackFormData) {
    try {
      const ok = await submitFeedback(values);
      if (!ok) {
        toast.error(t('error'));
        return;
      }
      onOpenChange(false);
      form.reset();
      toast.success(t('success'));
    } catch {
      toast.error(t('error'));
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            id="feedback-form"
            className="flex flex-col min-w-0 gap-y-4"
            onSubmit={form.handleSubmit(onSubmit)}
            noValidate
          >
            <FormField
              control={form.control}
              name="category"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('category.label')}</FormLabel>
                  <Select value={field.value ?? ''} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder={t('category.placeholder')} />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {FEEDBACK_CATEGORIES.map((category) => (
                        <SelectItem key={category} value={category}>
                          {t(`categories.${category}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="message"
              render={({ field }) => (
                <FormItem required>
                  <FormLabel>{t('message.label')}</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder={t('message.placeholder')}
                      rows={5}
                      maxLength={MAX_FEEDBACK_LENGTH}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('cancel')}
          </Button>
          <Button blue type="submit" form="feedback-form" disabled={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? t('submitting') : t('submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
