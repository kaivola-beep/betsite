import React, { useState } from 'react';
import { ChevronRight, ChevronLeft, Target, Gamepad2, CreditCard, Shield, CheckCircle } from 'lucide-react';

interface QuizAnswer {
  gamePreference: string[];
  depositMethod: string[];
  kycPreference: string;
  bonusType: string[];
  wageringPreference: string;
}

const CasinoQuiz = () => {
  const [currentStep, setCurrentStep] = useState(0);
  const [answers, setAnswers] = useState<QuizAnswer>({
    gamePreference: [],
    depositMethod: [],
    kycPreference: '',
    bonusType: [],
    wageringPreference: ''
  });
  const [showResults, setShowResults] = useState(false);

  const questions = [
    {
      id: 'gamePreference',
      title: 'What games do you enjoy most?',
      subtitle: 'Select all that apply',
      icon: Gamepad2,
      type: 'multiple',
      options: [
        { value: 'slots', label: 'Slot Machines', emoji: '🎰' },
        { value: 'sports', label: 'Sports Betting', emoji: '⚽' },
        { value: 'live', label: 'Live Casino', emoji: '🎲' },
        { value: 'poker', label: 'Poker', emoji: '♠️' },
        { value: 'blackjack', label: 'Blackjack', emoji: '🃏' },
        { value: 'roulette', label: 'Roulette', emoji: '🎡' }
      ]
    },
    {
      id: 'depositMethod',
      title: 'How do you prefer to deposit?',
      subtitle: 'Select your preferred payment methods',
      icon: CreditCard,
      type: 'multiple',
      options: [
        { value: 'visa', label: 'Visa/Mastercard', emoji: '💳' },
        { value: 'crypto', label: 'Cryptocurrency', emoji: '₿' },
        { value: 'paypal', label: 'PayPal', emoji: '💰' },
        { value: 'bank', label: 'Bank Transfer', emoji: '🏦' },
        { value: 'ewallet', label: 'E-wallets', emoji: '📱' },
        { value: 'prepaid', label: 'Prepaid Cards', emoji: '🎫' }
      ]
    },
    {
      id: 'kycPreference',
      title: 'Identity verification preference?',
      subtitle: 'Choose your comfort level with KYC',
      icon: Shield,
      type: 'single',
      options: [
        { value: 'no-kyc', label: 'No KYC Required', emoji: '🕶️', desc: 'Anonymous play preferred' },
        { value: 'minimal', label: 'Minimal Verification', emoji: '📧', desc: 'Email verification only' },
        { value: 'standard', label: 'Standard KYC', emoji: '🆔', desc: 'Full verification is fine' }
      ]
    },
    {
      id: 'bonusType',
      title: 'What bonuses interest you most?',
      subtitle: 'Select your preferred bonus types',
      icon: Target,
      type: 'multiple',
      options: [
        { value: 'signup', label: 'Welcome Bonuses', emoji: '🎁' },
        { value: 'free-spins', label: 'Free Spins', emoji: '🎡' },
        { value: 'cashback', label: 'Cashback Offers', emoji: '💸' },
        { value: 'reload', label: 'Reload Bonuses', emoji: '🔄' },
        { value: 'vip', label: 'VIP Programs', emoji: '👑' },
        { value: 'tournaments', label: 'Tournaments', emoji: '🏆' }
      ]
    },
    {
      id: 'wageringPreference',
      title: 'Wagering requirements preference?',
      subtitle: 'How do you feel about playthrough requirements?',
      icon: CheckCircle,
      type: 'single',
      options: [
        { value: 'none', label: 'No Wagering', emoji: '🚫', desc: 'I want to withdraw immediately' },
        { value: 'low', label: 'Low Wagering (≤35x)', emoji: '✅', desc: 'Reasonable requirements are okay' },
        { value: 'any', label: 'Any Wagering', emoji: '🎯', desc: 'I enjoy the challenge' }
      ]
    }
  ];

  const handleAnswerChange = (questionId: string, value: string, isMultiple: boolean) => {
    if (isMultiple) {
      const currentAnswers = answers[questionId as keyof QuizAnswer] as string[];
      const newAnswers = currentAnswers.includes(value)
        ? currentAnswers.filter(a => a !== value)
        : [...currentAnswers, value];
      setAnswers({ ...answers, [questionId]: newAnswers });
    } else {
      setAnswers({ ...answers, [questionId]: value });
    }
  };

  const nextStep = () => {
    if (currentStep < questions.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      setShowResults(true);
    }
  };

  const prevStep = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const resetQuiz = () => {
    setCurrentStep(0);
    setShowResults(false);
    setAnswers({
      gamePreference: [],
      depositMethod: [],
      kycPreference: '',
      bonusType: [],
      wageringPreference: ''
    });
  };

  const getRecommendations = () => {
    // This would typically connect to your filtering logic
    const recommendations = [
      {
        casino: 'CryptoSlots Casino',
        match: 95,
        reasons: ['Crypto payments', 'No KYC', 'Great slots selection'],
        logo: '🎰'
      },
      {
        casino: 'Lightning Casino',
        match: 88,
        reasons: ['No wagering cashback', 'Fast payouts', 'Mobile optimized'],
        logo: '⚡'
      },
      {
        casino: 'Bitcoin Blackjack',
        match: 82,
        reasons: ['Bitcoin deposits', 'Anonymous play', 'Live dealers'],
        logo: '₿'
      }
    ];
    return recommendations;
  };

  if (showResults) {
    const recommendations = getRecommendations();
    
    return (
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-8">
          <div className="text-6xl mb-4">🎯</div>
          <h2 className="text-3xl font-bold text-slate-900 mb-4">Your Perfect Casino Matches</h2>
          <p className="text-slate-600">Based on your preferences, here are our top recommendations:</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {recommendations.map((rec, index) => (
            <div key={index} className="bg-white rounded-xl border border-slate-200 p-6 hover:shadow-lg transition-shadow">
              <div className="text-center mb-4">
                <div className="text-4xl mb-2">{rec.logo}</div>
                <h3 className="font-bold text-slate-900 text-lg">{rec.casino}</h3>
                <div className="text-emerald-600 font-semibold">{rec.match}% Match</div>
              </div>
              
              <div className="space-y-2 mb-6">
                {rec.reasons.map((reason, i) => (
                  <div key={i} className="flex items-center space-x-2 text-sm text-slate-600">
                    <CheckCircle size={16} className="text-emerald-500" />
                    <span>{reason}</span>
                  </div>
                ))}
              </div>

              <button className="w-full bg-emerald-600 text-white py-3 rounded-lg font-semibold hover:bg-emerald-700 transition-colors">
                View Casino
              </button>
            </div>
          ))}
        </div>

        <div className="text-center">
          <button
            onClick={resetQuiz}
            className="bg-slate-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-slate-700 transition-colors"
          >
            Take Quiz Again
          </button>
        </div>
      </div>
    );
  }

  const currentQuestion = questions[currentStep];
  const currentAnswers = answers[currentQuestion.id as keyof QuizAnswer];
  const canProceed = Array.isArray(currentAnswers) ? currentAnswers.length > 0 : currentAnswers !== '';

  return (
    <div className="max-w-2xl mx-auto">
      {/* Progress Bar */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <span className="text-sm font-medium text-slate-600">
            Question {currentStep + 1} of {questions.length}
          </span>
          <span className="text-sm text-slate-600">
            {Math.round(((currentStep + 1) / questions.length) * 100)}% Complete
          </span>
        </div>
        <div className="w-full bg-slate-200 rounded-full h-2">
          <div
            className="bg-emerald-600 h-2 rounded-full transition-all duration-300"
            style={{ width: `${((currentStep + 1) / questions.length) * 100}%` }}
          />
        </div>
      </div>

      {/* Question */}
      <div className="bg-white rounded-xl border border-slate-200 p-8">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-100 rounded-full mb-4">
            <currentQuestion.icon className="text-emerald-600" size={32} />
          </div>
          <h2 className="text-2xl font-bold text-slate-900 mb-2">
            {currentQuestion.title}
          </h2>
          <p className="text-slate-600">{currentQuestion.subtitle}</p>
        </div>

        <div className="space-y-3">
          {currentQuestion.options.map((option) => (
            <label
              key={option.value}
              className={`flex items-center p-4 border-2 rounded-lg cursor-pointer transition-all ${
                (Array.isArray(currentAnswers) 
                  ? currentAnswers.includes(option.value)
                  : currentAnswers === option.value)
                  ? 'border-emerald-500 bg-emerald-50'
                  : 'border-slate-200 hover:border-slate-300'
              }`}
            >
              <input
                type={currentQuestion.type === 'multiple' ? 'checkbox' : 'radio'}
                name={currentQuestion.id}
                value={option.value}
                checked={Array.isArray(currentAnswers) 
                  ? currentAnswers.includes(option.value)
                  : currentAnswers === option.value}
                onChange={() => handleAnswerChange(currentQuestion.id, option.value, currentQuestion.type === 'multiple')}
                className="sr-only"
              />
              <div className="flex items-center space-x-4 flex-1">
                <span className="text-2xl">{option.emoji}</span>
                <div className="flex-1">
                  <div className="font-medium text-slate-900">{option.label}</div>
                  {option.desc && (
                    <div className="text-sm text-slate-600">{option.desc}</div>
                  )}
                </div>
              </div>
              <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center ${
                (Array.isArray(currentAnswers) 
                  ? currentAnswers.includes(option.value)
                  : currentAnswers === option.value)
                  ? 'border-emerald-500 bg-emerald-500'
                  : 'border-slate-300'
              }`}>
                {(Array.isArray(currentAnswers) 
                  ? currentAnswers.includes(option.value)
                  : currentAnswers === option.value) && (
                  <CheckCircle size={12} className="text-white" />
                )}
              </div>
            </label>
          ))}
        </div>

        {/* Navigation */}
        <div className="flex items-center justify-between mt-8">
          <button
            onClick={prevStep}
            disabled={currentStep === 0}
            className={`flex items-center space-x-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              currentStep === 0
                ? 'text-slate-400 cursor-not-allowed'
                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
            }`}
          >
            <ChevronLeft size={20} />
            <span>Previous</span>
          </button>

          <button
            onClick={nextStep}
            disabled={!canProceed}
            className={`flex items-center space-x-2 px-6 py-3 rounded-lg font-semibold transition-colors ${
              canProceed
                ? 'bg-emerald-600 text-white hover:bg-emerald-700'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            <span>{currentStep === questions.length - 1 ? 'Get Results' : 'Next'}</span>
            <ChevronRight size={20} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default CasinoQuiz