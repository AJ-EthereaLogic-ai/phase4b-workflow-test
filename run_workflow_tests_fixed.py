"""
Fixed automated workflow testing script.
Works with the actual ADWS workflow API.
"""

import asyncio
import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from adws.workflows import (
    BackendStandardWorkflow,
    BackendTDDWorkflow,
    FrontendStandardWorkflow,
    FrontendTDDWorkflow
)


def get_github_issue(issue_number: int) -> str:
    """Fetch GitHub issue body using gh CLI."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json", "body"],
            capture_output=True,
            text=True,
            check=True
        )
        issue_data = json.loads(result.stdout)
        return issue_data["body"]
    except Exception as e:
        raise Exception(f"Failed to fetch issue #{issue_number}: {e}")


class WorkflowTestRunner:
    """Automated test runner for all ADWS workflows."""

    def __init__(self):
        self.results: List[Dict] = []

    async def test_workflow(
        self,
        workflow_class,
        workflow_name: str,
        issue_number: int,
        **workflow_kwargs
    ) -> Dict:
        """Test a single workflow and return results."""
        print(f"\n{'=' * 80}")
        print(f"Testing: {workflow_name}")
        print(f"Issue #: {issue_number}")
        print(f"{'=' * 80}\n")

        start_time = datetime.now()

        try:
            # Fetch GitHub issue
            print(f"📥 Fetching GitHub issue #{issue_number}...")
            requirement = get_github_issue(issue_number)
            print(f"✅ Got requirement ({len(requirement)} chars)")

            # Initialize workflow
            print(f"🔧 Initializing {workflow_name}...")
            workflow = workflow_class(**workflow_kwargs)

            # Generate unique ADW ID
            adw_id = f"test-{workflow_name.lower()}-{issue_number}"

            # Execute workflow
            print(f"🚀 Executing workflow...")
            result = await workflow.execute(
                requirement=requirement,
                adw_id=adw_id,
                metadata={"issue_number": str(issue_number)}
            )

            duration = (datetime.now() - start_time).total_seconds()

            test_result = {
                "workflow": workflow_name,
                "issue_number": issue_number,
                "success": result.success,
                "duration_seconds": duration,
                "output": result.output if hasattr(result, 'output') else None,
                "error": None
            }

            if result.success:
                print(f"\n✅ {workflow_name} PASSED")
                print(f"   Duration: {duration:.2f}s")
                if hasattr(result, 'output') and result.output:
                    print(f"   Output preview: {result.output[:200]}...")
            else:
                print(f"\n❌ {workflow_name} FAILED")
                print(f"   Reason: Workflow reported failure")

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            test_result = {
                "workflow": workflow_name,
                "issue_number": issue_number,
                "success": False,
                "duration_seconds": duration,
                "error": str(e)
            }

            print(f"\n❌ {workflow_name} FAILED")
            print(f"   Error: {e}")

        self.results.append(test_result)
        return test_result

    async def run_all_tests(self):
        """Run all workflow tests."""
        print("\n" + "=" * 80)
        print("ADWS WORKFLOW AUTONOMOUS COMPLETION TESTS")
        print("=" * 80)

        # Test 1: Backend Standard
        await self.test_workflow(
            BackendStandardWorkflow,
            "BackendStandardWorkflow",
            issue_number=1,
            working_dir="app/server"
        )

        # Test 2: Backend TDD
        await self.test_workflow(
            BackendTDDWorkflow,
            "BackendTDDWorkflow",
            issue_number=2,
            working_dir="app/server"
        )

        # Test 3: Frontend Standard
        await self.test_workflow(
            FrontendStandardWorkflow,
            "FrontendStandardWorkflow",
            issue_number=3,
            working_dir="app/client"
        )

        # Test 4: Frontend TDD
        await self.test_workflow(
            FrontendTDDWorkflow,
            "FrontendTDDWorkflow",
            issue_number=4,
            working_dir="app/client"
        )

        # Generate report
        self.generate_report()

    def generate_report(self):
        """Generate test results report."""
        print("\n" + "=" * 80)
        print("TEST RESULTS SUMMARY")
        print("=" * 80 + "\n")

        passed = sum(1 for r in self.results if r["success"])
        failed = len(self.results) - passed

        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {passed / len(self.results) * 100:.1f}%\n")

        # Detailed results
        for result in self.results:
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{status} | {result['workflow']}")
            print(f"       Issue #{result['issue_number']}")
            print(f"       Duration: {result.get('duration_seconds', 0):.2f}s")
            if result.get("error"):
                print(f"       Error: {result['error']}")
            print()

        # Save report to JSON
        report_path = Path("workflow_test_results.json")
        with open(report_path, "w") as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "results": self.results
            }, f, indent=2)

        print(f"📄 Full report saved to: {report_path}")


async def main():
    """Main entry point."""
    runner = WorkflowTestRunner()
    await runner.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
