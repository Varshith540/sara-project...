from django.core.management.base import BaseCommand
from core.models import IndustryTrend
from core.gemini_service import get_trending_skills_with_gemini

class Command(BaseCommand):
    help = 'Fetches the latest hiring trends (keywords) from Gemini AI and updates the IndustryTrend database.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--sectors',
            nargs='+',
            type=str,
            default=['IT & Software', 'Non-IT', 'Vocational/Electrician'],
            help='List of sectors to update'
        )

    def handle(self, *args, **options):
        sectors = options['sectors']
        self.stdout.write(self.style.SUCCESS(f"Starting freshness check for {len(sectors)} sectors..."))

        for sector in sectors:
            self.stdout.write(f"Fetching trends for: {sector}")
            keywords = get_trending_skills_with_gemini(sector)
            
            if keywords:
                trend, created = IndustryTrend.objects.update_or_create(
                    sector=sector,
                    defaults={'keywords': keywords}
                )
                action = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(f"{action} trends for {sector}: {keywords[:3]}..."))
            else:
                self.stdout.write(self.style.WARNING(f"Failed to fetch trends for {sector}"))

        self.stdout.write(self.style.SUCCESS("Freshness check complete!"))
