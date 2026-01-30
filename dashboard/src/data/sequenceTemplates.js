// Default sequence templates for common outreach scenarios

export const DEFAULT_TEMPLATES = [
  {
    id: "3pl-cold-outreach",
    name: "3PL Cold Outreach",
    description: "5-step sequence targeting 3PL decision makers with email and phone follow-up",
    category: "3pl",
    steps: [
      {
        type: "email",
        delay_days: 0,
        template: "email_1",
        subject: "Warehouse automation for {{company_name}}",
        body: "Hi {{first_name}},\n\n{{personalization_sentence}}\n\nWe help 3PLs like {{company_name}} automate warehouse operations to cut labor costs by 40% and boost throughput 3x.\n\nWorth a 15-minute call?\n\nBest,\n{{sender_name}}"
      },
      {
        type: "wait",
        delay_days: 3
      },
      {
        type: "email",
        delay_days: 0,
        template: "email_2",
        subject: "Re: {{company_name}} automation",
        body: "Hi {{first_name}},\n\nFollowing up on my email about warehouse automation for {{company_name}}.\n\nWe recently helped a 200k sq ft 3PL reduce pick times by 60%. Happy to share the case study.\n\nOpen to a quick call this week?\n\n{{sender_name}}"
      },
      {
        type: "wait",
        delay_days: 4
      },
      {
        type: "call",
        delay_days: 0,
        script: "Hi {{first_name}}, this is {{sender_name}} from Intralog. I sent you a couple emails about warehouse automation for {{company_name}}. I wanted to reach out personally because we're seeing great results with 3PLs - our clients are cutting labor costs by 40% on average. Do you have 2 minutes to discuss how this could work for {{company_name}}?"
      }
    ]
  },
  {
    id: "warehouse-automation-full",
    name: "Warehouse Automation - Full Sequence",
    description: "7-step omnichannel sequence with email, call, and LinkedIn outreach",
    category: "warehouse_automation",
    steps: [
      {
        type: "email",
        delay_days: 0,
        template: "email_1",
        subject: "Warehouse automation opportunity at {{company_name}}",
        body: "{{personalization_sentence}}\n\nWe specialize in warehouse automation for companies like {{company_name}}. Our clients typically see 3x throughput gains and 40% labor cost reduction.\n\nOpen to exploring this?\n\n{{sender_name}}"
      },
      {
        type: "wait",
        delay_days: 3
      },
      {
        type: "linkedin_connect",
        delay_days: 0,
        message: "Hi {{first_name}}, I saw your role at {{company_name}} and thought I'd connect. We work with warehouse operations teams on automation projects."
      },
      {
        type: "wait",
        delay_days: 2
      },
      {
        type: "email",
        delay_days: 0,
        template: "email_2",
        subject: "Re: Warehouse automation at {{company_name}}",
        body: "Hi {{first_name}},\n\nWanted to follow up - are you currently exploring warehouse automation solutions?\n\nWe recently completed a project for a company with similar {{pain_theme}} challenges. Happy to share details.\n\n{{sender_name}}"
      },
      {
        type: "wait",
        delay_days: 4
      },
      {
        type: "call",
        delay_days: 0,
        script: "Hi {{first_name}}, {{sender_name}} from Intralog. Quick call about warehouse automation at {{company_name}}. I know {{pain_theme}} is a common challenge in your industry. We've helped similar companies achieve 3x throughput gains. Do you have 5 minutes to discuss?"
      },
      {
        type: "wait",
        delay_days: 3
      },
      {
        type: "linkedin_message",
        delay_days: 0,
        message: "Hi {{first_name}}, tried to reach you by email and phone about warehouse automation for {{company_name}}. Worth a quick call? Let me know if you're open to discussing."
      }
    ]
  },
  {
    id: "quick-email-followup",
    name: "Quick Email Follow-up",
    description: "Simple 2-email sequence for warm leads or quick outreach",
    category: "logistics",
    steps: [
      {
        type: "email",
        delay_days: 0,
        template: "email_1",
        subject: "Quick question about {{company_name}}",
        body: "Hi {{first_name}},\n\n{{personalization_sentence}}\n\nWe help logistics companies like {{company_name}} streamline operations and cut costs through automation.\n\nWorth a brief conversation?\n\n{{sender_name}}"
      },
      {
        type: "wait",
        delay_days: 4
      },
      {
        type: "email",
        delay_days: 0,
        template: "email_2",
        subject: "Re: {{company_name}}",
        body: "Hi {{first_name}},\n\nCircling back on my previous email. We've been helping companies in your space achieve significant operational improvements.\n\nOpen to a 10-minute intro call?\n\n{{sender_name}}"
      }
    ]
  },
  {
    id: "enterprise-multi-touch",
    name: "Enterprise Multi-Touch",
    description: "9-step enterprise sequence with all channels for high-value accounts",
    category: "warehouse_automation",
    steps: [
      {
        type: "email",
        delay_days: 0,
        template: "email_1"
      },
      {
        type: "wait",
        delay_days: 2
      },
      {
        type: "linkedin_connect",
        delay_days: 0,
        message: "Hi {{first_name}}, reaching out regarding warehouse automation opportunities at {{company_name}}."
      },
      {
        type: "wait",
        delay_days: 3
      },
      {
        type: "email",
        delay_days: 0,
        template: "email_2"
      },
      {
        type: "wait",
        delay_days: 3
      },
      {
        type: "call",
        delay_days: 0,
        script: "Enterprise-focused call script for {{first_name}} at {{company_name}} regarding {{pain_theme}}."
      },
      {
        type: "wait",
        delay_days: 2
      },
      {
        type: "linkedin_message",
        delay_days: 0,
        message: "Following up on my outreach - would love to connect about automation at {{company_name}}."
      },
      {
        type: "wait",
        delay_days: 5
      },
      {
        type: "email",
        delay_days: 0,
        template: "email_1",
        subject: "Final follow-up: {{company_name}} automation",
        body: "Hi {{first_name}},\n\nLast follow-up from me. If warehouse automation isn't a priority right now, totally understand.\n\nIf it becomes relevant in the future, feel free to reach out.\n\n{{sender_name}}"
      }
    ]
  }
];

export function getTemplatesByCategory(category) {
  if (!category) return DEFAULT_TEMPLATES;
  return DEFAULT_TEMPLATES.filter(t => t.category === category);
}

export function getTemplateById(id) {
  return DEFAULT_TEMPLATES.find(t => t.id === id);
}

export const TEMPLATE_CATEGORIES = [
  { id: "3pl", label: "3PL & Distribution", count: 1 },
  { id: "warehouse_automation", label: "Warehouse Automation", count: 2 },
  { id: "logistics", label: "Logistics & Supply Chain", count: 1 }
];
