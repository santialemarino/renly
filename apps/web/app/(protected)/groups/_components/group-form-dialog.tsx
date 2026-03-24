'use client';

import { useEffect, useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';
import { zodResolver } from '@hookform/resolvers/zod';
import { Check, ChevronsUpDown, X } from 'lucide-react';
import { AnimatePresence, motion } from 'motion/react';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';

import {
  Button,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@repo/ui/components';
import { cn } from '@repo/ui/lib';
import { createGroup, updateGroup } from '@/app/(protected)/groups/groups-actions';
import {
  buildGroupFormSchema,
  type GroupFormValues,
} from '@/app/(protected)/groups/groups-form-schema';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/form';
import type { InvestmentGroup } from '@/lib/api/groups';
import { ANIMATION_DEFAULT, ANIMATION_FAST } from '@/lib/constants/animations';

interface GroupFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  group?: InvestmentGroup;
  investments: { id: number; name: string }[];
  onSuccess?: () => void;
}

export function GroupFormDialog({
  open,
  onOpenChange,
  group,
  investments,
  onSuccess,
}: GroupFormDialogProps) {
  const t = useTranslations('groups');
  const tCommon = useTranslations('common');
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [comboboxOpen, setComboboxOpen] = useState(false);

  const isEdit = !!group;

  const schema = buildGroupFormSchema(tCommon('form.errors.required'));
  const form = useForm<GroupFormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: group?.name ?? '',
      investmentIds: group?.investmentIds ?? [],
    },
  });

  useEffect(() => {
    if (open) {
      form.reset({
        name: group?.name ?? '',
        investmentIds: group?.investmentIds ?? [],
      });
    }
  }, [open, group, form]);

  const selectedIds = form.watch('investmentIds') ?? [];
  const investmentMap = new Map(investments.map((inv) => [inv.id, inv.name]));

  function addInvestment(id: number) {
    const current = form.getValues('investmentIds') ?? [];
    if (!current.includes(id)) {
      form.setValue('investmentIds', [...current, id]);
    }
  }

  function removeInvestment(id: number) {
    const current = form.getValues('investmentIds') ?? [];
    form.setValue(
      'investmentIds',
      current.filter((i) => i !== id),
    );
  }

  function onSubmit(values: GroupFormValues) {
    startTransition(async () => {
      try {
        if (isEdit) {
          await updateGroup(group.id, values);
          toast.success(t('form.success.edit'));
        } else {
          await createGroup(values);
          toast.success(t('form.success.create'));
        }
        if (onSuccess) {
          onSuccess();
        } else {
          router.refresh();
        }
        onOpenChange(false);
      } catch {
        toast.error(isEdit ? t('form.error.edit') : t('form.error.create'));
      }
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? t('form.editTitle') : t('form.createTitle')}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form
            id="group-form"
            noValidate
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col gap-y-4"
          >
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel required>{t('form.name.label')}</FormLabel>
                  <FormControl>
                    <Input {...field} placeholder={t('form.name.placeholder')} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex flex-col gap-y-2">
              <FormLabel>{t('form.investments.label')}</FormLabel>

              {/* Selected investments as chips */}
              <AnimatePresence initial={false}>
                {selectedIds.length > 0 && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: ANIMATION_DEFAULT }}
                    className="flex flex-wrap gap-1.5 overflow-hidden"
                  >
                    <AnimatePresence initial={false}>
                      {selectedIds.map((id) => (
                        <motion.span
                          key={id}
                          initial={{ opacity: 0, scale: 0.8 }}
                          animate={{ opacity: 1, scale: 1 }}
                          exit={{ opacity: 0, scale: 0.8 }}
                          transition={{ duration: ANIMATION_FAST }}
                          className="inline-flex items-center gap-x-1 rounded-full border border-border bg-muted px-2.5 py-0.5 text-paragraph-mini"
                        >
                          {investmentMap.get(id) ?? `#${id}`}
                          <button
                            type="button"
                            onClick={() => removeInvestment(id)}
                            className="rounded-full p-0.5 text-muted-foreground transition-[opacity,transform,color] duration-150 hover:scale-110 hover:text-destructive focus-visible:outline-none focus-visible:scale-110"
                          >
                            <X className="size-3" />
                          </button>
                        </motion.span>
                      ))}
                    </AnimatePresence>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Investment combobox */}
              <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    className="h-9 w-full justify-between px-3 text-paragraph-sm font-normal text-muted-foreground"
                  >
                    {t('form.investments.placeholder')}
                    <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-(--radix-popover-trigger-width) p-0" align="start">
                  <Command>
                    <CommandInput placeholder={t('form.investments.placeholder')} />
                    <CommandList>
                      <CommandEmpty>{t('form.investments.empty')}</CommandEmpty>
                      <CommandGroup>
                        {investments.map((inv) => {
                          const isSelected = selectedIds.includes(inv.id);
                          return (
                            <CommandItem
                              key={inv.id}
                              value={inv.name}
                              onSelect={() =>
                                isSelected ? removeInvestment(inv.id) : addInvestment(inv.id)
                              }
                            >
                              <Check
                                className={cn(
                                  'size-4 shrink-0 transition-all duration-200',
                                  isSelected ? 'scale-100 opacity-100' : 'scale-0 opacity-0',
                                )}
                              />
                              {inv.name}
                            </CommandItem>
                          );
                        })}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>
          </form>
        </Form>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('form.cancel')}
          </Button>
          <Button blue type="submit" form="group-form" disabled={isPending}>
            {isPending ? t('form.cta.loading') : t('form.cta.label')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
