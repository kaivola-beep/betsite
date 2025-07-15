// Utility functions for BonusCard and related components

export const getWageringColor = (requirement: string) => {
  switch (requirement) {
    case 'none': return 'bg-green-100 text-green-800';
    case 'low': return 'bg-yellow-100 text-yellow-800';
    case 'medium': return 'bg-orange-100 text-orange-800';
    case 'high': return 'bg-red-100 text-red-800';
    default: return 'bg-slate-100 text-slate-800';
  }
};

export const getWageringText = (requirement: string) => {
  switch (requirement) {
    case 'none': return 'No Wagering';
    case 'low': return 'Low Wagering';
    case 'medium': return 'Medium Wagering';
    case 'high': return 'High Wagering';
    default: return requirement;
  }
}; 