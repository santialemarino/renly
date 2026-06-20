import { getTranslations } from 'next-intl/server';

interface HowItWorksStep {
  title: string;
  description: string;
}

// "How it works" — the numbered onboarding steps from the solution overview.
export async function LandingHowItWorks() {
  const t = await getTranslations('landing.howItWorks');
  const steps = t.raw('steps') as HowItWorksStep[];

  return (
    <section className="flex flex-col w-full max-w-3xl items-center self-center px-6 py-16 gap-y-10 bg-muted/30">
      <h2 className="text-heading-2 text-neutral-950 text-center">{t('title')}</h2>
      <ol className="flex flex-col w-full gap-y-6">
        {steps.map((step, index) => (
          <li key={step.title} className="flex items-start gap-x-4">
            <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-blue-800 text-paragraph-sm-semibold text-white">
              {index + 1}
            </span>
            <div className="flex flex-col gap-y-1">
              <h3 className="text-heading-5 text-neutral-950">{step.title}</h3>
              <p className="text-paragraph-sm text-muted-foreground">{step.description}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
