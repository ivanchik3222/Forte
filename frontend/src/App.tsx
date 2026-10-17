import { LoginPanel } from './components/LoginPanel';

const features = [
  {
    number: '01',
    title: 'Готов к API',
    description: 'Единая точка для запросов и подключение к локальному Flask backend.',
  },
  {
    number: '02',
    title: 'Состояние под контролем',
    description: 'Zustand хранит данные сессии и состояние входа без лишней обвязки.',
  },
  {
    number: '03',
    title: 'Пространство для роста',
    description: 'Типизированная структура и Tailwind v4 для следующих экранов.',
  },
];

function App() {
  return (
    <div className="relative min-h-screen overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute -top-52 right-[-12rem] h-[38rem] w-[38rem] rounded-full bg-forte-100/60 blur-3xl" />
      <header className="relative mx-auto flex max-w-7xl items-center justify-between px-6 py-7 lg:px-10">
        <a href="#top" className="flex items-center gap-3 focus-visible:rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-forte-500" aria-label="Forte case — наверх">
          <span className="flex h-10 w-10 items-end justify-center gap-0.5 rounded-xl bg-forte-500 pb-2.5" aria-hidden="true">
            <span className="h-2 w-1 rounded-full bg-white" />
            <span className="h-3.5 w-1 rounded-full bg-white" />
            <span className="h-5 w-1 rounded-full bg-white" />
          </span>
          <span className="text-xl font-extrabold tracking-tight text-ink">forte<span className="font-medium text-forte-500">/case</span></span>
        </a>
        <a href="#foundation" className="hidden text-sm font-semibold text-zinc-600 transition hover:text-forte-600 focus-visible:rounded focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-forte-500 sm:block">
          О проекте <span aria-hidden="true">↗</span>
        </a>
      </header>

      <main id="top" className="relative mx-auto max-w-7xl px-6 pb-16 lg:px-10">
        <div className="grid items-center gap-12 pb-14 pt-10 lg:grid-cols-[minmax(0,1.1fr)_minmax(360px,0.8fr)] lg:gap-20 lg:pb-24 lg:pt-20">
          <div>
            <p className="mb-7 inline-flex items-center gap-2 rounded-full border border-forte-100 bg-white/80 px-4 py-2 text-xs font-bold uppercase tracking-[0.16em] text-forte-700">
              <span className="h-1.5 w-1.5 rounded-full bg-forte-500" />
              Основа цифрового продукта
            </p>
            <h1 className="max-w-3xl text-5xl font-extrabold leading-[1.08] tracking-[-0.055em] text-ink sm:text-6xl xl:text-7xl">
              Идеи для банка <span className="text-forte-500">начинаются здесь.</span>
            </h1>
            <p className="mt-7 max-w-xl text-base leading-8 text-zinc-600 sm:text-lg">
              Стартовая платформа для кейса Forte: интерфейс, состояние приложения и связь с API готовы к развитию продукта.
            </p>
            <div className="mt-9 flex flex-wrap gap-2.5" aria-label="Технологии проекта">
              {['React + TypeScript', 'Tailwind CSS v4', 'Zustand'].map((item) => (
                <span key={item} className="rounded-full border border-zinc-200 bg-white px-4 py-2 text-sm font-medium text-zinc-700 shadow-sm">{item}</span>
              ))}
            </div>
          </div>
          <LoginPanel />
        </div>

        <section id="foundation" className="border-t border-zinc-200/80 pt-9" aria-labelledby="foundation-title">
          <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.2em] text-forte-600">Фундамент</p>
              <h2 id="foundation-title" className="mt-2 text-2xl font-bold tracking-tight text-ink sm:text-3xl">Всё на своих местах</h2>
            </div>
            <span className="text-sm text-zinc-400">Подготовлено для следующих этапов</span>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {features.map((feature) => (
              <article key={feature.number} className="rounded-2xl border border-zinc-200/80 bg-white/80 p-6 shadow-sm">
                <span className="text-sm font-bold text-forte-500">{feature.number}</span>
                <h3 className="mt-6 text-lg font-bold text-ink">{feature.title}</h3>
                <p className="mt-2 text-sm leading-6 text-zinc-500">{feature.description}</p>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="relative mx-auto flex max-w-7xl flex-wrap justify-between gap-3 border-t border-zinc-200/80 px-6 py-6 text-xs text-zinc-400 lg:px-10">
        <span>Forte case · демонстрационный проект</span>
        <span>Создано для разработки и проверки интеграции</span>
      </footer>
    </div>
  );
}

export default App;
