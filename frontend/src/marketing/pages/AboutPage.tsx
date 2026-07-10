// src/marketing/pages/AboutPage.tsx
import React from "react";
import { ArrowRight } from "lucide-react";
import MarketingEditorialShell from "../components/shared/MarketingEditorialShell";
import { useContactModal } from "../context/ContactModalContext";

import photoVladimir from "../components/assets/photos/vladimir.jpg";
import photoAnna from "../components/assets/photos/anna.jpg";
import photoDmitry from "../components/assets/photos/dmitry.jpg";
import photoIrina from "../components/assets/photos/irina.jpg";
import photoPavel from "../components/assets/photos/pavel.jpg";
import photoElena from "../components/assets/photos/elena.jpg";
import photoMaxim from "../components/assets/photos/maxim.jpg";
import photoOlga from "../components/assets/photos/olga.jpg";
import photoSergey from "../components/assets/photos/sergey.jpg";

interface ContentCard {
  title: string;
  text: string;
}

interface TeamMember {
  name: string;
  role: string;
  description: string;
  linkedin: string;
  photo: string;
}

const PRINCIPLES: ContentCard[] = [
  {
    title: "Сначала процесс, потом технологии",
    text: "Каждый сценарий анализа начинается с понимания реального юридического процесса. Мы сначала разбираем, как команда работает с документами, где тратит время и на каком этапе возникают узкие места, и только потом определяем, какие технологии действительно уместны.",
  },
  {
    title: "Проверяемость важнее убедительности",
    text: "Любой finding должен быть связан с документом, разделом и конкретным положением. Результат должен быть пригоден для проверки, обсуждения внутри команды и использования в дальнейшей работе.",
  },
  {
    title: "Сложность остается внутри продукта",
    text: "Пользователю не нужно разбираться в моделях, настройках и внутренней логике системы. Технологическая сложность должна быть задачей продукта, а не пользователя.",
  },
  {
    title: "Последовательность важнее случайной точности",
    text: "Юридическая работа требует не разового удачного ответа, а устойчивого и воспроизводимого процесса. Мы строим Steloom так, чтобы одинаковые документы проверялись по единым правилам и давали предсказуемый результат.",
  },
];

const VALUES: ContentCard[] = [
  {
    title: "Юридическая пригодность",
    text: "Каждый результат анализа должен быть понятен практикующему юристу, пригоден для review и дальнейшего обсуждения внутри команды или с клиентом.",
  },
  {
    title: "Контроль и прозрачность",
    text: "Для юридических документов особенно важны прозрачность обработки, возможность локального развертывания и контролируемое использование внешних сервисов.",
  },
  {
    title: "Надежность",
    text: "Мы строим полноценную систему обработки документов, включающую подготовку, структурирование, применение правил анализа и формирование воспроизводимых результатов.",
  },
  {
    title: "Практическая применимость",
    text: "Любая функция должна быть полезна в реальной работе юридической команды, а не только выглядеть убедительно во время демонстрации продукта.",
  },
];

const TEAM: TeamMember[] = [
  {
    name: "Vladimir Gorelov",
    role: "Основатель и руководитель продукта / разработки",
    description:
      "Отвечает за продуктовую логику Steloom, архитектуру document pipeline и интеграцию AI в юридические сценарии.",
    linkedin: "https://www.linkedin.com/in/example-vladimir",
    photo: photoVladimir,
  },
  {
    name: "Anna Kuznetsova",
    role: "Руководитель legal workflows",
    description:
      "Конструирует юридические playbooks для M&A, VC и корпоративных сценариев, чтобы выводы Steloom были пригодны для review.",
    linkedin: "https://www.linkedin.com/in/example-anna",
    photo: photoAnna,
  },
  {
    name: "Dmitry Morozov",
    role: "Ведущий ML / NLP инженер",
    description:
      "Разрабатывает модели для извлечения сущностей, связки выводов с источниками и анализа больших массивов договоров.",
    linkedin: "https://www.linkedin.com/in/example-dmitry",
    photo: photoDmitry,
  },
  {
    name: "Irina Sokolova",
    role: "Инженер document processing",
    description:
      "Отвечает за стабильный пайплайн загрузки, OCR, нормализации и разметки документов в Data Room.",
    linkedin: "https://www.linkedin.com/in/example-irina",
    photo: photoIrina,
  },
  {
    name: "Pavel Kravchenko",
    role: "Безопасность и инфраструктура",
    description:
      "Проектирует privacy-first архитектуру, модели доступа и контролируемое подключение облачных LLM.",
    linkedin: "https://www.linkedin.com/in/example-pavel",
    photo: photoPavel,
  },
  {
    name: "Elena Novikova",
    role: "Продукт и UX-дизайн",
    description:
      "Делает интерфейс Steloom пригодным для длительной работы юристов и аналитиков, а не только демо.",
    linkedin: "https://www.linkedin.com/in/example-elena",
    photo: photoElena,
  },
  {
    name: "Maxim Sergeev",
    role: "Customer Success",
    description:
      "Помогает командам интегрировать Steloom в их процессы, запускать пилоты и масштабировать сценарии.",
    linkedin: "https://www.linkedin.com/in/example-maxim",
    photo: photoMaxim,
  },
  {
    name: "Olga Petrova",
    role: "Data Analyst",
    description:
      "Собирает и анализирует метрики использования, помогает улучшать качество проверок и выводов.",
    linkedin: "https://www.linkedin.com/in/example-olga",
    photo: photoOlga,
  },
  {
    name: "Sergey Ivanov",
    role: "Backend инженер",
    description:
      "Разрабатывает backend Steloom, API для document pipeline и интеграцию с внешними системами.",
    linkedin: "https://www.linkedin.com/in/example-sergey",
    photo: photoSergey,
  },
];

const AboutPage: React.FC = () => {
  const { openContactModal } = useContactModal();

  return (
    <MarketingEditorialShell
      title="Мы автоматизируем подготовку информации, а не юридическое мышление"
      description="Steloom помогает юридическим командам быстрее готовить основу для анализа и принятия решений в сделках, due diligence и корпоративных проектах."
    >
      {/* Блок 1 — Hero extended body */}
      <div className="mb-16 max-w-3xl lg:mb-20">
        <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
          Продукт вырос из практической работы с юридическими документами, где
          значительная часть времени команды уходит не на саму оценку рисков,
          а на поиск нужной информации, проверку структуры документов,
          применение внутренних инструкций и подготовку основы для дальнейшего
          анализа.
        </p>
        <p className="mt-4 text-[0.9375rem] leading-[1.7] text-[#78756F]">
          Мы создаем инструмент, который берёт на себя эту повторяющуюся работу
          и помогает быстрее получать результаты проверки в форме, пригодной
          для review, обсуждения и принятия решений.
        </p>
      </div>

      {/* Блок 2 — Почему появился Steloom */}
      <div className="mb-16 lg:mb-20">
        <div className="rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-7 lg:p-9">
          <h2 className="max-w-2xl font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Почему появился Steloom
          </h2>

          <div className="mt-6 max-w-3xl space-y-4">
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Из опыта членов нашей команды и наших коллег в M&A,
              корпоративной практике и внутренних юридических функциях
              постепенно стало ясно, что у очень разных проектов есть общая
              проблема.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Сделки отличаются структурой бизнеса, набором документов,
              требованиями покупателей, внутренними политиками компаний
              и критериями оценки риска. Но в реальной работе юридическая
              команда почти всегда проходит один и тот же путь.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Нужно разобраться в массиве документов. Понять, какие из них
              действительно важны для анализа. Соотнести их с внутренними
              инструкциями и задачами конкретного проекта. Найти существенные
              положения. Проверить отклонения. Собрать findings. Подготовить
              материалы, на основании которых уже можно обсуждать риски
              и формировать выводы.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Именно эта часть работы чаще всего требует наибольшего объема
              времени и внимания. При этом она остается необходимой независимо
              от отрасли, юрисдикции или типа сделки.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Мы увидели, что требования проектов меняются, но сама логика
              юридической подготовки к анализу остается удивительно устойчивой.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Именно поэтому она стала отправной точкой для создания Steloom.
            </p>
            <p className="text-[0.9375rem] font-medium leading-[1.7] text-[#1A1917]">
              Мы решили автоматизировать подготовку информации, на которой
              строится юридический анализ.
            </p>
          </div>
        </div>
      </div>

      {/* Блок 3 — Что мы строим */}
      <div className="mb-16 lg:mb-20">
        <div className="rounded-2xl border border-[#E8E4DD] bg-white p-7 lg:p-9">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[#78756F]">
            Позиционирование
          </p>
          <h2 className="mt-4 max-w-3xl font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Steloom — инструмент для автоматизации повторяющейся работы
            с юридическими документами
          </h2>

          <div className="mt-6 max-w-3xl space-y-4">
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Steloom становится частью ежедневной работы юридической команды.
              Он помогает классифицировать документы, применять внутренние
              стандарты проверки и готовить материалы для review.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Платформа поддерживает работу как с отдельными договорами, так
              и с большими массивами документов, помогая команде использовать
              единую логику анализа и получать результаты в форме, пригодной
              для практической юридической работы.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              В результате юристы получают не разрозненные ответы,
              а структурированную основу для профессиональной оценки: findings
              с привязкой к источникам, DD grid по типам документов, материалы
              для review и более ясное понимание того, на что нужно смотреть
              в первую очередь.
            </p>
          </div>
        </div>
      </div>

      {/* Блок 4 — Наш подход */}
      <div className="mb-16 lg:mb-20">
        <div className="rounded-2xl border border-[#E8E4DD] bg-[#1A1917] p-7 lg:p-10">
          <div className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#A8A29E]">
            Подход
          </div>
          <h2 className="mt-4 max-w-2xl font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-white">
            Наш подход
          </h2>

          <div className="mt-6 max-w-3xl space-y-4">
            <p className="text-[0.9375rem] leading-[1.7] text-[#D6D0C7]">
              Хороший юридический инструмент должен упрощать работу
              специалиста, а не превращать её в работу с технологией.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#D6D0C7]">
              Мы не стремимся делать из юриста оператора сложной системы,
              которому нужно проходить длинный сценарий действий, разбираться
              во внутренней логике продукта или подстраивать свой рабочий
              процесс под интерфейс.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#D6D0C7]">
              Наша задача — сократить путь от загрузки документов до
              результата, который уже можно использовать в реальной
              юридической работе.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#D6D0C7]">
              Поэтому мы проектируем Steloom так, чтобы технологическая
              сложность оставалась внутри продукта, а пользователь работал
              с документами, результатами проверки и привычными юридическими
              сценариями.
            </p>
            <p className="text-[0.9375rem] font-medium leading-[1.7] text-white">
              Для нас важна не технология сама по себе, а то, насколько быстро
              юридическая команда может перейти от массива документов
              к профессиональному анализу.
            </p>
          </div>
        </div>
      </div>

      {/* Блок 5 — Как мы создаем Steloom */}
      <div className="mb-16 lg:mb-20">
        <div className="mb-8">
          <div className="eyebrow">Принципы</div>
          <h2 className="mt-4 font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Как мы создаем Steloom
          </h2>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {PRINCIPLES.map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-[#E8E4DD] bg-white p-6"
            >
              <h3 className="text-lg font-semibold text-[#1A1917]">
                {item.title}
              </h3>
              <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[#78756F]">
                {item.text}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Блок 6 — Что для нас важно */}
      <div className="mb-16 lg:mb-20">
        <div className="mb-8">
          <div className="eyebrow">Ценности</div>
          <h2 className="mt-4 font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Что для нас важно
          </h2>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {VALUES.map((item) => (
            <div
              key={item.title}
              className="rounded-2xl border border-[#E8E4DD] bg-white p-6"
            >
              <h3 className="text-lg font-semibold text-[#1A1917]">
                {item.title}
              </h3>
              <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[#78756F]">
                {item.text}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Блок 7 — Команда */}
      <div className="mb-16 lg:mb-20">
        <div className="mb-8">
          <div className="eyebrow">Команда</div>
          <h2 className="mt-4 max-w-2xl font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Команда
          </h2>

          <div className="mt-5 max-w-3xl space-y-4">
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Мы объединяем опыт юридического сопровождения сделок,
              корпоративной практики и разработки программных продуктов.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Именно сочетание юридической практики и инженерного опыта
              позволяет нам строить продукт, который учитывает контекст работы
              юридических команд, требования бизнеса и особенности внедрения
              в корпоративной среде.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Поэтому при разработке Steloom мы начинаем с анализа реального
              юридического процесса — и уже от него выстраиваем архитектуру
              продукта, логику сценариев и формат результата.
            </p>
            <p className="text-[0.9375rem] leading-[1.7] text-[#78756F]">
              Для нас важно не просто применять современные технологии,
              а делать их действительно полезными для ежедневной юридической
              работы.
            </p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {TEAM.map((member) => (
            <article
              key={member.name}
              className="overflow-hidden rounded-2xl border border-[#E8E4DD] bg-white"
            >
              <div className="aspect-[4/3] overflow-hidden bg-[#F3F0EB]">
                <img
                  src={member.photo}
                  alt={member.name}
                  className="h-full w-full object-cover"
                />
              </div>
              <div className="p-5">
                <h3 className="text-xl font-semibold text-[#1A1917]">
                  {member.name}
                </h3>
                <p className="mt-1 text-sm font-medium text-[#78756F]">
                  {member.role}
                </p>
                <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[#78756F]">
                  {member.description}
                </p>
              </div>
            </article>
          ))}
        </div>
      </div>

      {/* Блок 8 — Финальный CTA */}
      <div className="rounded-2xl border border-[#E8E4DD] bg-[#F3F0EB] p-7 lg:p-10">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="font-serif text-[clamp(1.75rem,3vw,2.5rem)] leading-tight tracking-[-0.03em] text-[#1A1917]">
            Давайте покажем Steloom на ваших документах
          </h2>
          <p className="mt-5 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Лучший способ оценить платформу — увидеть, как она работает
            с реальными юридическими документами.
          </p>
          <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Во время демонстрации мы покажем полный процесс работы: от
            загрузки документов и выбора сценария проверки до формирования
            findings с привязкой к источникам, DD grid и материалов,
            пригодных для дальнейшего review.
          </p>
          <p className="mt-3 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Если у вас есть собственные договоры или материалы проекта,
            мы можем использовать их в качестве примера, чтобы показать работу
            платформы в условиях, максимально приближенных к вашим задачам.
          </p>
          <p className="mt-4 text-[0.9375rem] leading-[1.7] text-[#78756F]">
            Именно так мы видим роль технологий в юридической работе:
            помогать специалисту быстрее готовить информацию для анализа,
            сохраняя за человеком профессиональное суждение и принятие
            решений.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <button
              type="button"
              onClick={openContactModal}
              className="cta-primary"
            >
              Запросить демонстрацию
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={openContactModal}
              className="cta-secondary"
            >
              Связаться с командой
            </button>
          </div>
        </div>
      </div>
    </MarketingEditorialShell>
  );
};

export default AboutPage;

