import { ArgumentGenerated, DebateTurn, FeedbackReady } from '@/hooks/useWebSocket'

export const mockResponses = {
  single: {
    personalInjury: {
      arguments: [
        {
          type: 'argument_generated' as const,
          agent: 'Legal Analyst',
          content: `After analyzing your argument, I can see you're establishing the property owner's duty of care despite contributory negligence. This is a strong foundation.

Your argument correctly focuses on the property owner's independent duty to maintain safe premises. Under premises liability law, property owners have a non-delegable duty to keep their property reasonably safe for lawful visitors, regardless of the visitor's potential negligence.`,
          thinking: `The user is dealing with a contributory/comparative negligence defense. I need to help them strengthen their premises liability argument while addressing the defendant's texting defense.`,
          timestamp: Date.now()
        },
        {
          type: 'argument_generated' as const,
          agent: 'Legal Strategist',
          content: `To strengthen your argument, consider these key points:

1. **Separate Duties Doctrine**: Emphasize that the property owner's duty to maintain safe conditions exists independently of any contributory negligence by the plaintiff.

2. **Foreseeability**: Argue that distracted pedestrians are foreseeable, and property owners must account for this reality when maintaining their premises.

3. **Comparative Negligence**: Even if the plaintiff was partially at fault, in most jurisdictions this only reduces damages proportionally, not eliminate liability entirely.

4. **Notice and Knowledge**: Focus on whether the property owner knew or should have known about the hazardous condition and failed to remedy it or provide adequate warning.`,
          thinking: `Providing specific legal doctrines and strategic approaches to counter the contributory negligence defense.`,
          timestamp: Date.now() + 1000
        }
      ],
      feedback: {
        type: 'feedback_ready' as const,
        recommendations: [
          'Gather evidence of how long the hazardous condition existed',
          'Document similar incidents or complaints about the same hazard',
          'Obtain expert testimony on property maintenance standards',
          'Research local precedents on comparative negligence in premises liability cases'
        ],
        strengths: [
          'Correctly identifies the independent duty of property owners',
          'Understands that contributory negligence doesn\'t eliminate liability',
          'Focus on premises liability law is appropriate'
        ],
        weaknesses: [
          'Need more specific case law citations',
          'Should address the degree of plaintiff\'s distraction',
          'Could strengthen causation argument between hazard and injury'
        ]
      }
    }
  },
  debate: {
    nonCompete: {
      turns: [
        {
          type: 'debate_turn' as const,
          turn: 1,
          prosecutor: {
            argument: `Your Honor, the non-compete clause in question is a valid, negotiated agreement between sophisticated parties. The employee received valuable consideration including access to proprietary information, specialized training, and client relationships. 

The clause is narrowly tailored: it's limited to 12 months, covers only direct competitors, and applies solely within the specific geographic region where the company operates. This reasonable restriction protects legitimate business interests without unduly restraining trade.

The employee cannot now claim ignorance or unfairness after benefiting from the company's investments in their development.`,
            thinking: `Opening with contract validity and reasonable restrictions. Need to emphasize the exchange of value and narrow scope to counter California's strong anti-noncompete stance.`
          },
          defender: {
            response: `Your Honor, California Business and Professions Code Section 16600 is unequivocal: "Except as provided in this chapter, every contract by which anyone is restrained from engaging in a lawful profession, trade, or business of any kind is to that extent void."

This statute reflects California's fundamental public policy favoring employee mobility and competition. The California Supreme Court in Edwards v. Arthur Andersen (2008) explicitly rejected the "narrow restraint" exception that other states recognize.

No amount of consideration or claimed business interests can overcome California's statutory prohibition. The law protects not just the employee's right to work, but also promotes innovation and economic growth through free movement of talent.`,
            thinking: `Leading with the statutory prohibition and Supreme Court precedent. California law is clear and leaves little room for exceptions.`
          }
        },
        {
          type: 'debate_turn' as const,
          turn: 2,
          prosecutor: {
            argument: `Counsel misapplies Section 16600. The statute has recognized exceptions, particularly for trade secret protection and ownership interests. Our client isn't seeking to prevent all employment, merely protecting confidential information and customer relationships developed at significant expense.

Furthermore, if the employment agreement contains a choice-of-law provision selecting another state's law, California courts have enforced such provisions when the employer has substantial contacts with that state. Application Group, Inc. v. Hunter Group established this principle.

The employee acknowledged these restrictions and received substantial compensation accordingly. Allowing them to immediately join a competitor would constitute unjust enrichment.`,
            thinking: `Pivoting to the trade secret exception and choice-of-law arguments. These are the narrow paths that might work even in California.`
          },
          defender: {
            response: `The trade secret exception is precisely that - an exception for trade secrets, not a backdoor for general non-compete agreements. California's Uniform Trade Secrets Act provides the exclusive remedy for trade secret misappropriation. The employer cannot use a non-compete clause to achieve what trade secret law specifically addresses.

Regarding choice-of-law, the California Supreme Court in Whitewater West Industries v. Alleshouse held that California's prohibition on non-compete agreements reflects a fundamental public policy that cannot be circumvented through choice-of-law provisions when California has a material interest.

The "unjust enrichment" argument fails because the employee earned their compensation through past services rendered. Future employment rights cannot be bargained away under California law, regardless of consideration.`,
            thinking: `Distinguishing trade secret law from non-compete enforcement and addressing the choice-of-law argument with recent California Supreme Court precedent.`
          }
        },
        {
          type: 'debate_turn' as const,
          turn: 3,
          prosecutor: {
            argument: `Even accepting California's strict approach, equitable remedies remain available. The doctrine of inevitable disclosure, while limited, can prevent an employee from taking a position where they would inevitably use or disclose trade secrets.

Additionally, non-solicitation provisions targeting specific clients with whom the employee worked are more likely to survive scrutiny than broad non-compete clauses. We seek only to protect established client relationships, not to prevent competition entirely.

The employee's bad faith is relevant here - evidence shows they downloaded client lists and proprietary data before resignation, suggesting intentional misappropriation rather than innocent job mobility.`,
            thinking: `Final attempt focusing on narrower theories: inevitable disclosure and non-solicitation, plus introducing bad faith conduct to strengthen the equitable argument.`
          },
          defender: {
            response: `The "inevitable disclosure" doctrine has been largely rejected in California. In Schlage Lock v. Whyte, the court held that this doctrine cannot create an implied non-compete agreement where express agreements are void.

Non-solicitation agreements face the same scrutiny under Section 16600 when they substantially restrict business operations. The California Supreme Court in Dowell v. Biosense Webster confirmed that even client-specific restrictions are void if they restrain business competition.

As for the alleged bad faith conduct, if the employer has evidence of trade secret theft, they should pursue appropriate remedies under the Uniform Trade Secrets Act or criminal law, not attempt to enforce an illegal non-compete agreement. The validity of the contract clause stands independent of any alleged misconduct.

California's policy is clear: promote innovation and competition through employee mobility. This court should void the non-compete clause as required by law.`,
            thinking: `Closing by dismantling each remaining argument and returning to California's fundamental policy. The law strongly favors my position.`
          }
        }
      ],
      feedback: {
        type: 'feedback_ready' as const,
        recommendations: [
          'Lawyer A should focus more on federal law preemption arguments if applicable',
          'Lawyer B could strengthen position with economic impact studies on non-compete agreements',
          'Both sides should address recent FTC proposed rules on non-compete agreements',
          'Consider alternative protective mechanisms like garden leave or retention bonuses'
        ],
        strengths: [
          'Lawyer A: Creative arguments using choice-of-law and trade secret exceptions',
          'Lawyer B: Strong command of California statutory and case law',
          'Both: Well-structured arguments with appropriate legal citations'
        ],
        weaknesses: [
          'Lawyer A: Fighting uphill battle against clear statutory prohibition',
          'Lawyer B: Could address more policy considerations',
          'Both: Limited discussion of practical business alternatives'
        ]
      }
    }
  }
}

export function getMockResponse(mode: 'single' | 'debate', userInput: string) {
  // Check if the input matches our test cases
  const isPersonalInjury = userInput.toLowerCase().includes('personal injury') || 
                          userInput.toLowerCase().includes('texting while walking')
  
  const isNonCompete = userInput.toLowerCase().includes('non-compete') || 
                       userInput.toLowerCase().includes('california')
  
  if (mode === 'single' && isPersonalInjury) {
    return mockResponses.single.personalInjury
  }
  
  if (mode === 'debate' && isNonCompete) {
    return mockResponses.debate.nonCompete
  }
  
  // Default responses for other inputs
  if (mode === 'single') {
    return {
      arguments: [
        {
          type: 'argument_generated' as const,
          agent: 'Legal Analyst',
          content: `I've analyzed your legal argument. While I cannot connect to the backend system currently, here's a general framework for strengthening your position:

1. Establish the legal foundation with relevant statutes and case law
2. Address potential counterarguments preemptively  
3. Ensure your facts support each element of your legal theory
4. Consider procedural requirements and deadlines`,
          thinking: 'Providing general legal analysis framework as fallback.',
          timestamp: Date.now()
        }
      ],
      feedback: {
        type: 'feedback_ready' as const,
        recommendations: [
          'Research relevant case law in your jurisdiction',
          'Strengthen factual support for key claims',
          'Consider alternative legal theories',
          'Prepare for likely counterarguments'
        ],
        strengths: ['Clear legal theory', 'Organized presentation'],
        weaknesses: ['Needs more specific case citations', 'Could address more counterarguments']
      }
    }
  }
  
  return {
    turns: [
      {
        type: 'debate_turn' as const,
        turn: 1,
        prosecutor: {
          argument: 'Opening argument establishing the primary legal position...',
          thinking: 'Setting up the foundation of the argument.'
        },
        defender: {
          response: 'Counter-argument addressing the key legal issues...',
          thinking: 'Identifying weaknesses in the opposing position.'
        }
      }
    ],
    feedback: {
      type: 'feedback_ready' as const,
      recommendations: ['Consider additional legal theories', 'Strengthen factual support'],
      strengths: ['Clear arguments from both sides'],
      weaknesses: ['Could use more specific case law']
    }
  }
}