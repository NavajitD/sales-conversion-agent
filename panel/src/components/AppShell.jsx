import { Activity, BarChart3, Clock3, Menu, Moon, PhoneCall, Sparkles, Sun, Users, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { cn } from '../lib/utils';

const navItems = [
  {
    path: '/live-monitor',
    label: 'Live Monitor',
    description: 'Track active conversations, sentiment and strategy updates as they happen.',
    icon: Activity,
  },
  {
    path: '/parents',
    label: 'Parents / Leads',
    description: 'Manage the full post-demo parent pipeline and callback readiness.',
    icon: Users,
  },
  {
    path: '/call-history',
    label: 'Call History',
    description: 'Review completed call attempts and drill into the reasoning timeline.',
    icon: PhoneCall,
  },
  {
    path: '/callbacks',
    label: 'Callbacks Queue',
    description: 'Stay ahead of pending callbacks, attempts and follow-up commitments.',
    icon: Clock3,
  },
  {
    path: '/analytics',
    label: 'Analytics',
    description: 'Understand outcomes, objections, strategies and sentiment trends.',
    icon: BarChart3,
  },
];

export default function AppShell() {
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [darkMode, setDarkMode] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('aria-theme') !== 'light';
    }
    return true;
  });

  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    document.documentElement.classList.toggle('light', !darkMode);
    localStorage.setItem('aria-theme', darkMode ? 'dark' : 'light');
  }, [darkMode]);

  const currentPage = useMemo(
    () => navItems.find((item) => item.path === location.pathname) ?? navItems[0],
    [location.pathname],
  );

  return (
    <div className={cn('min-h-screen', darkMode ? 'bg-slate-950 text-slate-100' : 'bg-white text-slate-900')}>
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:rounded-md focus:bg-violet-600 focus:px-4 focus:py-2 focus:text-white">Skip to content</a>
      <div className="flex min-h-screen">
        <div
          className={cn(
            'fixed inset-0 z-30 backdrop-blur-sm transition lg:hidden',
            darkMode ? 'bg-slate-950/70' : 'bg-slate-900/30',
            sidebarOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0',
          )}
          onClick={() => setSidebarOpen(false)}
        />

        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r px-5 py-6 transition-transform duration-300 lg:static lg:translate-x-0',
            darkMode ? 'border-slate-800/80 bg-slate-950/95' : 'border-slate-200 bg-white',
            sidebarOpen ? 'translate-x-0' : '-translate-x-full',
          )}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-2xl border border-[#7C3AED]/20 bg-[#7C3AED]/15 p-3 text-violet-200">
                <Sparkles className="h-5 w-5" />
              </div>
              <div>
                <p className={cn('text-sm font-semibold', darkMode ? 'text-white' : 'text-slate-900')}>Aria CRM</p>
                <p className={cn('text-xs', darkMode ? 'text-slate-400' : 'text-slate-500')}>Vedantu voice conversion desk</p>
              </div>
            </div>
            <button
              type="button"
              className={cn('inline-flex rounded-2xl border p-2 lg:hidden', darkMode ? 'border-slate-800 text-slate-400' : 'border-slate-200 text-slate-500')}
              onClick={() => setSidebarOpen(false)}
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <nav className="mt-8 space-y-2" aria-label="Main navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.path}
                  to={item.path}
                  aria-current={location.pathname === item.path ? 'page' : undefined}
                  className={({ isActive }) =>
                    cn(
                      'flex items-start gap-3 rounded-2xl border px-4 py-3 transition',
                      isActive
                        ? 'border-[#7C3AED]/35 bg-[#7C3AED]/15 text-white shadow-[0_10px_30px_-15px_rgba(124,58,237,0.8)]'
                        : darkMode
                          ? 'border-transparent text-slate-400 hover:border-slate-800 hover:bg-slate-900/80 hover:text-slate-100'
                          : 'border-transparent text-slate-600 hover:border-slate-200 hover:bg-slate-100 hover:text-slate-900',
                    )
                  }
                >
                  <Icon className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
                  <div>
                    <p className="text-sm font-medium">{item.label}</p>
                    <p className={cn('mt-1 text-xs leading-5', darkMode ? 'text-slate-500' : 'text-slate-400')}>{item.description}</p>
                  </div>
                </NavLink>
              );
            })}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className={cn('sticky top-0 z-20 border-b backdrop-blur-xl', darkMode ? 'border-slate-800/80 bg-slate-950/85' : 'border-slate-200 bg-white/85')}>
            <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-4 px-4 py-4 sm:px-6 lg:px-8">
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  className={cn('inline-flex rounded-2xl border p-2 lg:hidden', darkMode ? 'border-slate-800 bg-slate-900/70 text-slate-300' : 'border-slate-200 bg-white text-slate-600')}
                  onClick={() => setSidebarOpen(true)}
                >
                  <Menu className="h-5 w-5" />
                </button>
                <div>
                  <p className={cn('text-xl font-semibold tracking-tight', darkMode ? 'text-white' : 'text-slate-900')}>Aria CRM</p>
                  <p className={cn('text-sm', darkMode ? 'text-slate-400' : 'text-slate-500')}>Post-Demo Parent Conversion</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setDarkMode(!darkMode)}
                  className={cn(
                    'inline-flex rounded-full border p-2 transition',
                    darkMode ? 'border-slate-700 bg-slate-900/70 text-slate-300 hover:bg-slate-800 hover:text-white' : 'border-slate-300 bg-slate-100 text-slate-600 hover:bg-slate-200 hover:text-slate-900'
                  )}
                  title={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
                  aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
                >
                  {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                </button>
              </div>
            </div>
          </header>

          <main id="main-content" className="flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <div className="mx-auto max-w-7xl space-y-6">
              <div>
                <p className={cn('text-xs uppercase tracking-[0.28em]', darkMode ? 'text-violet-300' : 'text-violet-600')} aria-hidden="true">Voice agent command center</p>
                <h1 className={cn('mt-2 text-3xl font-semibold tracking-tight', darkMode ? 'text-white' : 'text-slate-900')}>{currentPage.label}</h1>
                <p className={cn('mt-2 max-w-3xl text-sm leading-6', darkMode ? 'text-slate-400' : 'text-slate-600')}>{currentPage.description}</p>
              </div>
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
