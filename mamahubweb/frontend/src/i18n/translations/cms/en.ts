export const cmsEn = {
  pages: {
    faq: {
      title: 'Frequently Asked Questions',
      description: 'MamaHub FAQ — ordering, delivery, returns, and account help.',
    },
    contact: {
      title: 'Contact Us',
      description: 'Contact MamaHub customer support in Qatar.',
      intro:
        '<p>We love helping families find the perfect toy. Reach out anytime — our team is happy to help.</p>',
    },
    terms: {
      title: 'Terms and Conditions',
      description: 'MamaHub terms of service for online toy purchases in Qatar.',
      html: `
<p><em>Last updated: September 2026</em></p>
<h2>1. Acceptance of terms</h2>
<p>By accessing mamahub.store or placing an order, you agree to these Terms and Conditions.</p>
<h2>2. Products and pricing</h2>
<p>Prices are shown in Qatari Riyals (QAR) and may change without notice. Errors may be corrected and affected orders cancelled with a full refund.</p>
<h2>3. Orders and payment</h2>
<p>An order is confirmed once you receive an order confirmation email. Payment must be completed using approved methods at checkout.</p>
<h2>4. Delivery and pickup</h2>
<p>Delivery times are estimates. Risk of loss passes to you upon delivery to your address or upon store pickup.</p>
<h2>5. Returns and refunds</h2>
<p>Returns are subject to our Return Policy. Refunds are issued to the original payment method after inspection.</p>
<h2>6. Governing law</h2>
<p>These terms are governed by the laws of the State of Qatar.</p>
<p>Questions? Email <a href="mailto:legal@mamahub.store">legal@mamahub.store</a>.</p>
`.trim(),
    },
    privacy: {
      title: 'Privacy Policy',
      description: 'How MamaHub collects, uses, and protects your personal data.',
      html: `
<p><em>Last updated: September 2026</em></p>
<p>We protect your personal data and never sell customer information to third parties.</p>
<h2>Information we collect</h2>
<p>We collect information you provide when creating an account, placing orders, or contacting support — such as name, email, phone, and delivery address.</p>
<h2>How we use your information</h2>
<p>We use your data to process orders, deliver products, provide customer support, and improve our store.</p>
<h2>Cookies and analytics</h2>
<p>We use cookies to keep you signed in, remember your cart, and understand how visitors use our site.</p>
<h2>Sharing with third parties</h2>
<p>We do not sell your personal information. We share data only with trusted service providers under strict confidentiality agreements.</p>
<h2>Your rights</h2>
<p>You may request access to, correction of, or deletion of your personal data by emailing privacy@mamahub.store.</p>
<h2>Children's privacy</h2>
<p>Our website is intended for adults. We do not knowingly collect personal information from children under 13 without parental consent.</p>
`.trim(),
    },
    returns: {
      title: 'Return Policy',
      description: 'MamaHub return policy for toys and gifts in Qatar.',
      html: `
<p>Unopened items in original packaging may be returned within 14 days with proof of purchase.</p>
<p>Safety-sealed products must remain sealed. Opened or used toys may not be eligible unless defective.</p>
<p>Email hello@mamahub.store with your order number to start a return.</p>
`.trim(),
    },
  },
  faq: {
    empty: 'No FAQ items published yet.',
    stillHaveQuestions: 'Still have questions?',
    contactTeam: 'Contact our team',
    sections: [
      {
        title: 'Ordering',
        items: [
          {
            question: 'How do I place an order?',
            answer:
              'Browse our catalog, add items to your cart, and checkout with delivery or store pickup. You can shop as a guest or create an account to track orders.',
          },
          {
            question: 'Can I modify or cancel my order?',
            answer:
              'Orders can be modified or cancelled within 30 minutes of placement. After that, contact our support team before dispatch.',
          },
          {
            question: 'Do you offer gift wrapping?',
            answer:
              'Yes. Choose gift wrap on the product page when you add an item to your cart. Gift receipts hide item prices for the recipient.',
          },
        ],
      },
      {
        title: 'Delivery',
        items: [
          {
            question: 'Where do you deliver?',
            answer:
              'We deliver across Qatar, including Doha, Al Wakrah, and Al Khor. Enter your address at checkout to confirm availability.',
          },
          {
            question: 'How long does delivery take?',
            answer:
              'Standard delivery is 1–3 business days. Same-day delivery may be available in select Doha zones for orders placed before 2:00 PM.',
          },
          {
            question: 'What are the delivery fees?',
            answer:
              'Delivery starts at QAR 15. Orders over QAR 200 qualify for free standard delivery within Doha.',
          },
        ],
      },
      {
        title: 'Returns & exchanges',
        items: [
          {
            question: 'What is your return policy?',
            answer:
              'Unopened items in original packaging may be returned within 14 days with proof of purchase. Safety-sealed products must remain sealed.',
          },
          {
            question: 'How do I start a return?',
            answer:
              'Email hello@mamahub.store with your order number. Our team will share return instructions and a reference number.',
          },
        ],
      },
      {
        title: 'Payments & account',
        items: [
          {
            question: 'Which payment methods do you accept?',
            answer: 'Major credit and debit cards, Apple Pay, and cash on delivery in eligible areas.',
          },
          {
            question: 'How do loyalty points work?',
            answer: 'Earn points on every purchase when signed in. Redeem points at checkout for discounts.',
          },
        ],
      },
    ],
  },
  contact: {
    sendMessage: 'Send us a message',
    formHint: 'Your message is saved and our team will respond by email.',
    fullName: 'Full name',
    email: 'Email',
    subject: 'Subject',
    message: 'Message',
    sending: 'Sending…',
    send: 'Send message',
    successMessage:
      'Thanks for reaching out! We have received your message and will reply within one business day.',
    subjects: [
      'Order inquiry',
      'Delivery question',
      'Return or exchange',
      'Product recommendation',
      'Other',
    ],
    cards: [
      {
        title: 'Customer support',
        lines: ['hello@mamahub.store', '+974 4000 1234', 'Sun–Thu, 9:00 AM – 6:00 PM'],
      },
      {
        title: 'Store location',
        lines: ['MamaHub Flagship Store', 'West Bay, Doha, Qatar', 'Near City Center Mall'],
      },
      {
        title: 'Delivery hotline',
        lines: ['delivery@mamahub.store', '+974 4000 5678', 'Daily, 8:00 AM – 10:00 PM'],
      },
    ],
  },
  shell: {
    loading: 'Loading page...',
    notFound: 'Page not found',
    retrying: 'Retrying…',
    tryAgain: 'Try again',
    loadFailed: 'We could not load this page.',
  },
} as const
