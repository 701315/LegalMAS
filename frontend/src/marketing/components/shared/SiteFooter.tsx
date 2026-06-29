// src/marketing/components/shared/SiteFooter.tsx

import React from "react";
import { Link } from "react-router-dom";
import SteloomWordmark from "./primitives/SteloomWordmark";
import { SITE_NAV, SITE_CTA } from "../../content/siteNav";

const LEGAL_LINKS = [
  { label: "Terms of Use",    href: "/legal/terms"   },
  { label: "Privacy Policy",  href: "/legal/privacy" },
  { label: "Cookie Policy",   href: "/legal/cookies" },
  { label: "Security Policy", href: "/legal/security"},
];

const SiteFooter: React.FC = () => (
  <footer
    className="border-t border-[#E5E2DA] bg-[#F1EFEA]"
    data-header-theme="light"
  >
    <div className="mx-auto w-full max-w-[1280px] px-4 py-16 sm:px-6 lg:px-10 xl:px-12">

      {/* ── Main grid ─────────────────────────────────────── */}
      <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-[1.8fr_0.8fr_0.8fr_1fr] lg:gap-8">

        {/* Brand */}
        <div>
          <Link
            to="/"
            aria-label="Steloom — home"
            className="inline-flex text-stone-900 transition-opacity hover:opacity-50"
          >
            <SteloomWordmark height={28} />
          </Link>

          <p className="mt-4 max-w-xs text-sm leading-7 text-stone-500">
            The intelligence layer for legal work.
            Playbook-driven review, source-linked outputs
            and controllable document workflows for M&A
            and corporate legal teams.
          </p>

          {/* Contact */}
          <div className="mt-6 space-y-2">
            <a
              href="mailto:hello@steloom.com"
              className="block text-sm text-stone-500 transition-colors hover:text-stone-900"
            >
              hello@steloom.com
            </a>
            <a
              href="tel:+79219125351"
              className="block text-sm text-stone-500 transition-colors hover:text-stone-900"
            >
              +7 921 912 53 51
            </a>
          </div>
        </div>

        {/* Product nav */}
        <div>
          <p className="mb-4 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
            Product
          </p>
          <ul className="space-y-2.5">
            {SITE_NAV.map((item) => (
              <li key={item.href}>
                <Link
                  to={item.href}
                  className="text-sm text-stone-500 transition-colors hover:text-stone-900"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>

        {/* Quick links */}
        <div>
          <p className="mb-4 text-[11px] font-medium uppercase tracking-[0.18em] text-stone-400">
            Quick links
          </p>
          <ul className="space-y-2.5">
            <li>
              <Link
                to={SITE_CTA.demo.href}
                className="text-sm text-stone-500 transition-colors hover:text-stone-900"
              >
                Request demo
              </Link>
            </li>
            <li>
              <Link
                to={SITE_CTA.login.href}
                className="text-sm text-stone-500 transition-colors hover:text-stone-900"
              >
                Log in
              </Link>
            </li>
          </ul>
        </div>

        {/* Big wordmark — desktop only */}
        <div className="hidden items-start justify-end lg:flex">
          <Link
            to="/"
            aria-label="Steloom — home"
            className="text-stone-900 transition-opacity hover:opacity-40"
          >
            <SteloomWordmark height={80} />
          </Link>
        </div>

      </div>

      {/* ── Bottom bar ────────────────────────────────────── */}
      <div className="mt-12 flex flex-col gap-4 border-t border-[#E5E2DA] pt-8 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-stone-400">
          © 2026 Steloom. All rights reserved.
        </p>

        <div className="flex flex-wrap gap-x-5 gap-y-2">
          {LEGAL_LINKS.map((l) => (
            <Link
              key={l.href}
              to={l.href}
              className="text-xs text-stone-400 transition-colors hover:text-stone-700"
            >
              {l.label}
            </Link>
          ))}
        </div>
      </div>

    </div>
  </footer>
);

export default SiteFooter;


