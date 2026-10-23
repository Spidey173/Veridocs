export interface DocumentClause {
  id: string;
  title: string;
  section: string;
  page: number;
  content: string;
  highlightWords?: string[];
  category?: "compensation" | "liability" | "termination" | "governance" | "financials";
}

export interface ContradictionItem {
  id: string;
  title: string;
  category: "Payment Terms" | "Liability" | "Termination" | "Jurisdiction";
  severity: "high" | "medium" | "low";
  docAClauseId: string;
  docBClauseId: string;
  docAText: string;
  docBText: string;
  diffSummary: string;
}

export interface DemoCitation {
  citation_id: string;
  source_file: string;
  page: number;
  clauseId: string;
  highlighted_text: string;
}

export interface DemoClaim {
  claim: string;
  status: "verified" | "inferred" | "hallucinated";
  numeric_grounded: boolean;
  best_source_page: number;
  clauseId: string;
}

export interface DemoQA {
  id: string;
  question: string;
  answer: string;
  citations: DemoCitation[];
  claims: DemoClaim[];
  ragTriad: {
    context_relevance: number;
    groundedness: number;
    answer_relevance: number;
    numeric_accuracy: number;
    retrieval_pipeline: string;
  };
}

export interface DemoScenario {
  id: string;
  name: string;
  subtitle: string;
  type: "comparison" | "single_qa";
  docA: {
    name: string;
    version: string;
    pages: number;
    clauses: DocumentClause[];
  };
  docB?: {
    name: string;
    version: string;
    pages: number;
    clauses: DocumentClause[];
  };
  contradictions?: ContradictionItem[];
  presetQuestions: DemoQA[];
}

export const DEMO_SCENARIOS: DemoScenario[] = [
  {
    id: "contracts-comparison",
    name: "Master Services Agreement vs. 2024 Amendment",
    subtitle: "Forensic cross-document contract discrepancy audit & clause diffing",
    type: "comparison",
    docA: {
      name: "MSA_2023_Original.pdf",
      version: "v1.2 (Active 2023)",
      pages: 2,
      clauses: [
        {
          id: "docA-sec1",
          title: "Section 1.1 — Scope of Engagement",
          section: "1.1",
          page: 1,
          content: "Provider agrees to deliver enterprise cloud architecture and document intelligence integrations according to Statement of Work schedules approved by Client.",
          highlightWords: ["enterprise cloud architecture", "document intelligence integrations"],
          category: "governance"
        },
        {
          id: "docA-sec3",
          title: "Section 3.1 — Professional Compensation & Fees",
          section: "3.1",
          page: 1,
          content: "Client shall remit to Provider a fixed monthly retainer of $15,000 USD, payable Net 30 days upon receipt of monthly itemized invoice. Late disbursements shall accrue 1.0% interest per calendar month.",
          highlightWords: ["fixed monthly retainer of $15,000 USD", "Net 30 days"],
          category: "compensation"
        },
        {
          id: "docA-sec5",
          title: "Section 5.2 — Limitation of Direct Liability",
          section: "5.2",
          page: 2,
          content: "In no event shall either party's aggregate monetary liability arising out of or related to this Agreement exceed $1,000,000 USD or the total fees paid during the preceding twelve (12) month period, whichever is lower.",
          highlightWords: ["exceed $1,000,000 USD", "whichever is lower"],
          category: "liability"
        },
        {
          id: "docA-sec8",
          title: "Section 8.4 — Mutual Termination for Convenience",
          section: "8.4",
          page: 2,
          content: "Either party may terminate this Agreement without cause upon thirty (30) days prior written formal notice transmitted via registered mail to the respective legal contact.",
          highlightWords: ["thirty (30) days prior written formal notice"],
          category: "termination"
        }
      ]
    },
    docB: {
      name: "MSA_2024_Amendment_Signed.pdf",
      version: "v2.0 (Amended 2024)",
      pages: 2,
      clauses: [
        {
          id: "docB-sec1",
          title: "Section 1.1 — Augmented Statement of Work",
          section: "1.1",
          page: 1,
          content: "Provider scope is hereby augmented to encompass multi-region deployment governance, automated data lifecycle pruning, and on-premises vector storage acceleration.",
          highlightWords: ["multi-region deployment governance", "automated data lifecycle pruning"],
          category: "governance"
        },
        {
          id: "docB-sec3",
          title: "Section 3.1 — Revised Retainer & Accelerated Terms",
          section: "3.1",
          page: 1,
          content: "Effective January 1, 2024, the monthly retainer fee is hereby increased to $22,500 USD per month. Invoices are payable under accelerated Net 15 days terms to ensure dedicated engineering capacity.",
          highlightWords: ["increased to $22,500 USD per month", "accelerated Net 15 days"],
          category: "compensation"
        },
        {
          id: "docB-sec5",
          title: "Section 5.2 — Expanded Enterprise Liability Cap",
          section: "5.2",
          page: 2,
          content: "The mutual aggregate liability cap specified in Section 5.2 of the Original Agreement is modified to $2,500,000 USD to reflect expanded cloud infrastructure and high-volume data processing obligations.",
          highlightWords: ["modified to $2,500,000 USD", "reflect expanded cloud infrastructure"],
          category: "liability"
        },
        {
          id: "docB-sec8",
          title: "Section 8.4 — Extended Notice & 15-Day Cure Window",
          section: "8.4",
          page: 2,
          content: "Termination without cause shall henceforth require sixty (60) days advance written notice, accompanied by a mandatory fifteen (15) day cure opportunity for any unresolved technical escalations.",
          highlightWords: ["sixty (60) days advance written notice", "fifteen (15) day cure opportunity"],
          category: "termination"
        }
      ]
    },
    contradictions: [
      {
        id: "contra-1",
        title: "Monthly Retainer Discrepancy (+$7,500/mo)",
        category: "Payment Terms",
        severity: "high",
        docAClauseId: "docA-sec3",
        docBClauseId: "docB-sec3",
        docAText: "Fixed monthly retainer of $15,000 USD, payable Net 30 days.",
        docBText: "Monthly retainer increased to $22,500 USD per month, payable Net 15 days.",
        diffSummary: "+$7,500 (+50%) recurring fee increase and payment window compressed by 15 days."
      },
      {
        id: "contra-2",
        title: "Aggregate Liability Cap Discrepancy (+$1.5M)",
        category: "Liability",
        severity: "high",
        docAClauseId: "docA-sec5",
        docBClauseId: "docB-sec5",
        docAText: "Aggregate monetary liability shall not exceed $1,000,000 USD or 12-mo fees.",
        docBText: "Mutual aggregate liability cap modified to $2,500,000 USD.",
        diffSummary: "150% expansion in ceiling financial liability exposure across both parties."
      },
      {
        id: "contra-3",
        title: "Termination Notice Period Doubled",
        category: "Termination",
        severity: "medium",
        docAClauseId: "docA-sec8",
        docBClauseId: "docB-sec8",
        docAText: "Termination without cause upon thirty (30) days prior written notice.",
        docBText: "Termination without cause requires sixty (60) days advance notice + 15-day cure window.",
        diffSummary: "Notice requirement extended from 30 to 60 calendar days with mandatory remediation period."
      }
    ],
    presetQuestions: [
      {
        id: "q-retainer",
        question: "What is the monthly retainer fee and payment terms in the 2024 amendment?",
        answer: "Under Section 3.1 of the 2024 First Amendment, the monthly retainer fee is $22,500 USD per month, payable under accelerated Net 15 days terms [Page 1]. This supersedes the previous $15,000 USD retainer and Net 30 terms.",
        citations: [
          {
            citation_id: "c-1",
            source_file: "MSA_2024_Amendment_Signed.pdf",
            page: 1,
            clauseId: "docB-sec3",
            highlighted_text: "monthly retainer fee is hereby increased to $22,500 USD per month. Invoices are payable under accelerated Net 15 days terms"
          }
        ],
        claims: [
          {
            claim: "Monthly retainer fee is $22,500 USD per month under Section 3.1",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 1,
            clauseId: "docB-sec3"
          },
          {
            claim: "Invoices are payable under accelerated Net 15 days terms",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 1,
            clauseId: "docB-sec3"
          },
          {
            claim: "Supersedes previous $15,000 USD retainer and Net 30 terms",
            status: "inferred",
            numeric_grounded: true,
            best_source_page: 1,
            clauseId: "docA-sec3"
          }
        ],
        ragTriad: {
          context_relevance: 0.96,
          groundedness: 0.99,
          answer_relevance: 0.95,
          numeric_accuracy: 1.0,
          retrieval_pipeline: "Hybrid BM25 + FAISS (RRF k=60)"
        }
      },
      {
        id: "q-liability",
        question: "How did the liability cap change between the original MSA and the amendment?",
        answer: "Section 5.2 of the Original Agreement established a liability cap of $1,000,000 USD [Page 2]. The 2024 Amendment modified this cap to $2,500,000 USD [Page 2], representing a 150% expansion in liability limit to cover expanded cloud data workloads.",
        citations: [
          {
            citation_id: "c-2",
            source_file: "MSA_2024_Amendment_Signed.pdf",
            page: 2,
            clauseId: "docB-sec5",
            highlighted_text: "liability cap specified in Section 5.2 of the Original Agreement is modified to $2,500,000 USD"
          },
          {
            citation_id: "c-3",
            source_file: "MSA_2023_Original.pdf",
            page: 2,
            clauseId: "docA-sec5",
            highlighted_text: "aggregate monetary liability arising out of or related to this Agreement exceed $1,000,000 USD"
          }
        ],
        claims: [
          {
            claim: "Original Agreement established a liability cap of $1,000,000 USD",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 2,
            clauseId: "docA-sec5"
          },
          {
            claim: "2024 Amendment modified this cap to $2,500,000 USD",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 2,
            clauseId: "docB-sec5"
          },
          {
            claim: "Represents a 150% expansion in overall liability limit",
            status: "inferred",
            numeric_grounded: true,
            best_source_page: 2,
            clauseId: "docB-sec5"
          }
        ],
        ragTriad: {
          context_relevance: 0.95,
          groundedness: 0.98,
          answer_relevance: 0.94,
          numeric_accuracy: 1.0,
          retrieval_pipeline: "Hybrid BM25 + FAISS (RRF k=60)"
        }
      },
      {
        id: "q-termination",
        question: "What are the rules for terminating the contract without cause?",
        answer: "Under Section 8.4 of the 2024 Amendment, termination without cause requires sixty (60) days advance written notice, plus a mandatory fifteen (15) day technical cure window [Page 2]. In the original 2023 contract, only 30 days notice was required.",
        citations: [
          {
            citation_id: "c-4",
            source_file: "MSA_2024_Amendment_Signed.pdf",
            page: 2,
            clauseId: "docB-sec8",
            highlighted_text: "sixty (60) days advance written notice, accompanied by a mandatory fifteen (15) day cure opportunity"
          }
        ],
        claims: [
          {
            claim: "Termination without cause requires 60 days advance written notice",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 2,
            clauseId: "docB-sec8"
          },
          {
            claim: "Includes mandatory 15-day technical cure opportunity",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 2,
            clauseId: "docB-sec8"
          }
        ],
        ragTriad: {
          context_relevance: 0.93,
          groundedness: 0.97,
          answer_relevance: 0.92,
          numeric_accuracy: 1.0,
          retrieval_pipeline: "Hybrid BM25 + FAISS (RRF k=60)"
        }
      }
    ]
  },
  {
    id: "sec-financials",
    name: "Apex Enterprise Solutions FY2024 10-K Report",
    subtitle: "Financial statement auditing & lexical grounding verification",
    type: "single_qa",
    docA: {
      name: "Apex_FY2024_Annual_Report.pdf",
      version: "SEC Filing Form 10-K",
      pages: 3,
      clauses: [
        {
          id: "fin-p1",
          title: "Item 1 — Fiscal Year 2024 Financial Overview",
          section: "Item 1",
          page: 1,
          content: "The company reported total consolidated revenue of $14.5 million in fiscal year 2024, representing an increase of 28% year-over-year compared to $11.3 million reported in fiscal year 2023. Gross profit margins reached 78.4%.",
          highlightWords: ["total consolidated revenue of $14.5 million", "increase of 28% year-over-year", "78.4%"],
          category: "financials"
        },
        {
          id: "fin-p2",
          title: "Item 7 — Operating Expenses & R&D Capital Allocation",
          section: "Item 7",
          page: 2,
          content: "Research and development expenditures totaled $3.2 million, focused on CPU ONNX inference engine optimization and sub-5ms heuristic verification pipelines. Cloud infrastructure hosting costs declined 18% following zero-torch migration.",
          highlightWords: ["totaled $3.2 million", "declined 18%"],
          category: "financials"
        },
        {
          id: "fin-p3",
          title: "Item 10 — Executive Leadership Appointments",
          section: "Item 10",
          page: 3,
          content: "In November 2023, the Board of Directors appointed Dr. Sarah Connor as Chief Technology Officer. The agreement includes a standard 36-month vesting period.",
          highlightWords: ["appointed Dr. Sarah Connor as Chief Technology Officer", "November 2023"],
          category: "governance"
        }
      ]
    },
    presetQuestions: [
      {
        id: "q-fin-rev",
        question: "What was the total revenue in fiscal year 2024 and how much did it grow?",
        answer: "Consolidated revenue reached $14.5 million in fiscal year 2024, representing a 28% year-over-year growth compared to $11.3 million in fiscal year 2023 with 78.4% gross margins [Page 1].",
        citations: [
          {
            citation_id: "cf-1",
            source_file: "Apex_FY2024_Annual_Report.pdf",
            page: 1,
            clauseId: "fin-p1",
            highlighted_text: "total consolidated revenue of $14.5 million in fiscal year 2024, representing an increase of 28% year-over-year"
          }
        ],
        claims: [
          {
            claim: "Consolidated revenue reached $14.5 million in fiscal year 2024",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 1,
            clauseId: "fin-p1"
          },
          {
            claim: "Represents 28% year-over-year growth compared to $11.3 million in FY2023",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 1,
            clauseId: "fin-p1"
          },
          {
            claim: "Gross profit margins reached 78.4%",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 1,
            clauseId: "fin-p1"
          }
        ],
        ragTriad: {
          context_relevance: 0.97,
          groundedness: 0.99,
          answer_relevance: 0.98,
          numeric_accuracy: 1.0,
          retrieval_pipeline: "Hybrid BM25 + FAISS (RRF k=60)"
        }
      },
      {
        id: "q-fin-rd",
        question: "How much did the company invest in R&D and what was the result?",
        answer: "R&D expenditures totaled $3.2 million targeting CPU ONNX inference and verification pipelines, resulting in an 18% decline in cloud infrastructure hosting costs [Page 2].",
        citations: [
          {
            citation_id: "cf-2",
            source_file: "Apex_FY2024_Annual_Report.pdf",
            page: 2,
            clauseId: "fin-p2",
            highlighted_text: "Research and development expenditures totaled $3.2 million ... hosting costs declined 18%"
          }
        ],
        claims: [
          {
            claim: "R&D expenditures totaled $3.2 million",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 2,
            clauseId: "fin-p2"
          },
          {
            claim: "Cloud hosting costs declined 18%",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 2,
            clauseId: "fin-p2"
          }
        ],
        ragTriad: {
          context_relevance: 0.94,
          groundedness: 0.98,
          answer_relevance: 0.96,
          numeric_accuracy: 1.0,
          retrieval_pipeline: "Hybrid BM25 + FAISS (RRF k=60)"
        }
      },
      {
        id: "q-sarah-board",
        question: "Did Sarah Connor appoint the Board of Directors?",
        answer: "⚠️ Grounding Engine Alert: The text specifies that the Board of Directors appointed Dr. Sarah Connor as Chief Technology Officer [Page 3]. Stating that Sarah Connor appointed the Board is a syntactic role reversal not supported by the document.",
        citations: [
          {
            citation_id: "cf-3",
            source_file: "Apex_FY2024_Annual_Report.pdf",
            page: 3,
            clauseId: "fin-p3",
            highlighted_text: "the Board of Directors appointed Dr. Sarah Connor as Chief Technology Officer"
          }
        ],
        claims: [
          {
            claim: "Board of Directors appointed Dr. Sarah Connor as Chief Technology Officer",
            status: "verified",
            numeric_grounded: true,
            best_source_page: 3,
            clauseId: "fin-p3"
          },
          {
            claim: "Sarah Connor appointed the Board of Directors",
            status: "hallucinated",
            numeric_grounded: false,
            best_source_page: 3,
            clauseId: "fin-p3"
          }
        ],
        ragTriad: {
          context_relevance: 0.88,
          groundedness: 0.85,
          answer_relevance: 0.91,
          numeric_accuracy: 1.0,
          retrieval_pipeline: "Hybrid BM25 + FAISS (RRF k=60)"
        }
      }
    ]
  }
];
