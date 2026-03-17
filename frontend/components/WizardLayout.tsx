"use client";

import { Sidebar } from "./Sidebar";
import { StepIndicator } from "./StepIndicator";

interface WizardLayoutProps {
  children: React.ReactNode;
  currentStep: number;
}

export function WizardLayout({ children, currentStep }: WizardLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <div className="border-b border-surface-3 bg-surface-0">
          <StepIndicator currentStep={currentStep} />
        </div>
        <div className="flex-1 overflow-y-auto px-8 py-6">
          {children}
        </div>
      </main>
    </div>
  );
}
