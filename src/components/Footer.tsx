import React from 'react';
import { Star, Mail, Phone, MapPin } from 'lucide-react';

export default function Footer() {
  return (
    <footer className="bg-slate-900 text-white mt-16">
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-8">
          {/* Brand */}
          <div>
            <div className="flex items-center space-x-3 mb-4">
              <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-xl flex items-center justify-center">
                <Star className="text-white" size={24} />
              </div>
              <div>
                <h3 className="text-xl font-bold">BonusHunter</h3>
                <p className="text-slate-400 text-sm">Find the best casino bonuses</p>
              </div>
            </div>
            <p className="text-slate-400 text-sm leading-relaxed">
              Your trusted source for comparing casino bonuses and finding the best deals online. 
              We help you make informed decisions with transparent reviews and real user feedback.
            </p>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="font-semibold mb-4">Quick Links</h4>
            <ul className="space-y-2">
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Casino Reviews</a></li>
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Bonus Guide</a></li>
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Payment Methods</a></li>
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Responsible Gaming</a></li>
            </ul>
          </div>

          {/* Support */}
          <div>
            <h4 className="font-semibold mb-4">Support</h4>
            <ul className="space-y-2">
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Help Center</a></li>
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Contact Us</a></li>
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Terms of Service</a></li>
              <li><a href="#" className="text-slate-400 hover:text-white transition-colors text-sm">Privacy Policy</a></li>
            </ul>
          </div>

          {/* Contact */}
          <div>
            <h4 className="font-semibold mb-4">Contact Info</h4>
            <div className="space-y-3">
              <div className="flex items-center space-x-3">
                <Mail size={16} className="text-slate-400" />
                <span className="text-slate-400 text-sm">support@bonushunter.com</span>
              </div>
              <div className="flex items-center space-x-3">
                <Phone size={16} className="text-slate-400" />
                <span className="text-slate-400 text-sm">+1 (555) 123-4567</span>
              </div>
              <div className="flex items-center space-x-3">
                <MapPin size={16} className="text-slate-400" />
                <span className="text-slate-400 text-sm">New York, NY</span>
              </div>
            </div>
          </div>
        </div>

        <div className="border-t border-slate-800 mt-8 pt-8">
          <div className="flex flex-col md:flex-row items-center justify-between">
            <div className="text-slate-400 text-sm mb-4 md:mb-0">
              © 2024 BonusHunter. All rights reserved.
            </div>
            <div className="text-slate-400 text-sm">
              <span className="mr-4">🔞 18+ Only</span>
              <span>Gamble Responsibly</span>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}