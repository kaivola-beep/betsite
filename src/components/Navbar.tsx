import React from 'react';
import { motion } from 'framer-motion';
import { Menu, X } from 'lucide-react';

const Logo = () => (
  <div className="w-10 h-10">
    <svg width="100%" height="100%" viewBox="0 0 480 480" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" xml:space="preserve" xmlns:serif="http://www.serif.com/" style={{fillRule:"evenodd", clipRule:"evenodd", strokeLinejoin:"round", strokeMiterlimit:2}}>
      <g transform="matrix(47.5579,0,0,47.5579,-142.832,-141.674)">
        <path d="M8.644,11.773C7.92,11.773 7.209,11.515 6.801,10.959L6.657,11.614L4,13L4.287,11.614L6.222,3L8.591,3L7.907,6.036C8.459,5.442 8.973,5.222 9.631,5.222C11.052,5.222 12,6.14 12,7.819C12,9.551 10.908,11.773 8.644,11.773ZM9.552,8.31C9.552,9.111 8.973,9.719 8.222,9.719C7.801,9.719 7.42,9.564 7.17,9.292L7.538,7.703C7.814,7.432 8.13,7.277 8.499,7.277C9.065,7.277 9.552,7.69 9.552,8.31Z" style={{fill:"white"}}/>
      </g>
    </svg>
  </div>
);

const Navbar = () => {
  const [isOpen, setIsOpen] = React.useState(false);

  return (
    <motion.nav
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      className="fixed top-6 right-6 transform z-50 bg-slate-800/80 backdrop-blur-xl border border-slate-700/50 rounded-full px-6 py-3"
    >
      <div className="grid grid-cols-3 items-center gap-4">
        {/* Logo - Left side */}
        <div className="flex items-center space-x-3 justify-self-start">
          <Logo />
          <span className="text-white font-semibold text-lg">FlowPay</span>
        </div>
        
        {/* Navigation Menu - Center */}
        <div className="hidden md:flex items-center space-x-8 justify-self-center">
          <a href="#" className="text-slate-300 hover:text-white transition-colors text-sm">Personal</a>
          <a href="#" className="text-slate-300 hover:text-white transition-colors text-sm">Business</a>
          <a href="#" className="text-slate-300 hover:text-white transition-colors text-sm">Platform</a>
          <a href="#" className="text-slate-300 hover:text-white transition-colors text-sm">Help</a>
        </div>

        {/* Auth buttons - Right side */}
        <div className="hidden md:flex items-center space-x-4 justify-self-end">
          <button className="text-slate-300 hover:text-white transition-colors text-sm whitespace-nowrap">
            Log in
          </button>
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            className="bg-lime-400 text-slate-900 px-4 py-2 rounded-full text-sm font-medium hover:bg-lime-300 transition-colors whitespace-nowrap"
          >
            Register
          </motion.button>
        </div>

        {/* Mobile menu button */}
        <button
          className="md:hidden text-white justify-self-end"
          onClick={() => setIsOpen(!isOpen)}
        >
          {isOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
    </motion.nav>
  );
};

export default Navbar;