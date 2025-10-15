# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from .decorators import log_io

logger = logging.getLogger(__name__)


class GitHubAnalyzer:
    """GitHub repository analyzer for tech selection."""

    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub analyzer.

        Args:
            token: GitHub personal access token (optional, but increases rate limit)
        """
        self.token = token or os.getenv("GITHUB_API_TOKEN")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Any:
        """Make a request to GitHub API with error handling."""
        url = f"{self.base_url}/{endpoint}"
        try:
            with httpx.Client() as client:
                response = client.get(url, headers=self.headers, params=params, timeout=10.0)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"GitHub API request failed for {endpoint}: {e}")
            return None

    def get_repo_info(self, owner: str, repo: str) -> Dict:
        """Get basic repository information."""
        data = self._make_request(f"repos/{owner}/{repo}")
        if not data:
            return {}

        return {
            "name": data.get("full_name", ""),
            "description": data.get("description", "N/A"),
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "watchers": data.get("watchers_count", 0),
            "open_issues": data.get("open_issues_count", 0),
            "language": data.get("language", "N/A"),
            "license": data.get("license", {}).get("name", "N/A"),
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "homepage": data.get("homepage", ""),
            "topics": data.get("topics", []),
            "default_branch": data.get("default_branch", "main"),
            "size": data.get("size", 0),
            "archived": data.get("archived", False),
        }

    def analyze_commit_frequency(
        self, owner: str, repo: str, months: int = 3
    ) -> Dict:
        """Analyze commit frequency for the last N months."""
        since = (datetime.now() - timedelta(days=months * 30)).isoformat()
        commits = self._make_request(
            f"repos/{owner}/{repo}/commits", params={"since": since, "per_page": 100}
        )

        if not commits:
            return {
                "total_commits": 0,
                "commits_per_week": 0,
                "commits_per_month": 0,
                "analysis_period_months": months,
            }

        total_commits = len(commits)
        weeks = months * 4
        return {
            "total_commits": total_commits,
            "commits_per_week": round(total_commits / weeks, 2) if weeks > 0 else 0,
            "commits_per_month": round(total_commits / months, 2) if months > 0 else 0,
            "analysis_period_months": months,
        }

    def analyze_contributors(self, owner: str, repo: str) -> Dict:
        """Analyze repository contributors."""
        contributors = self._make_request(
            f"repos/{owner}/{repo}/contributors", params={"per_page": 100}
        )

        if not contributors:
            return {"total_contributors": 0, "top_contributors": []}

        top_5 = contributors[:5] if len(contributors) >= 5 else contributors
        return {
            "total_contributors": len(contributors),
            "top_contributors": [
                {"username": c.get("login"), "contributions": c.get("contributions")}
                for c in top_5
            ],
        }

    def analyze_issues(self, owner: str, repo: str) -> Dict:
        """Analyze issue response time and status."""
        # Get closed issues from last 6 months
        since = (datetime.now() - timedelta(days=180)).isoformat()
        closed_issues = self._make_request(
            f"repos/{owner}/{repo}/issues",
            params={"state": "closed", "since": since, "per_page": 100},
        )

        open_issues = self._make_request(
            f"repos/{owner}/{repo}/issues", params={"state": "open", "per_page": 100}
        )

        if not closed_issues:
            closed_issues = []
        if not open_issues:
            open_issues = []

        # Calculate average close time
        close_times = []
        for issue in closed_issues[:30]:  # Analyze last 30 closed issues
            if "pull_request" in issue:  # Skip PRs
                continue
            created = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
            closed = datetime.fromisoformat(issue["closed_at"].replace("Z", "+00:00"))
            close_times.append((closed - created).days)

        avg_close_days = (
            round(sum(close_times) / len(close_times), 2) if close_times else 0
        )

        return {
            "open_issues_count": len(open_issues),
            "closed_issues_analyzed": len(close_times),
            "average_close_time_days": avg_close_days,
            "open_close_ratio": (
                round(len(open_issues) / len(closed_issues), 2)
                if closed_issues
                else 0
            ),
        }

    def analyze_pull_requests(self, owner: str, repo: str) -> Dict:
        """Analyze pull request merge rate and discussion quality."""
        # Get recent PRs
        prs = self._make_request(
            f"repos/{owner}/{repo}/pulls",
            params={"state": "all", "per_page": 100, "sort": "updated"},
        )

        if not prs:
            return {
                "total_prs_analyzed": 0,
                "merged_count": 0,
                "merge_rate": 0,
                "avg_comments": 0,
                "avg_review_time_days": 0,
            }

        merged = [pr for pr in prs if pr.get("merged_at")]
        closed_not_merged = [
            pr for pr in prs if pr.get("closed_at") and not pr.get("merged_at")
        ]

        # Calculate average comments and review time
        total_comments = sum(pr.get("comments", 0) for pr in prs[:30])
        avg_comments = round(total_comments / min(30, len(prs)), 2) if prs else 0

        # Calculate review time for merged PRs
        review_times = []
        for pr in merged[:20]:
            created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
            merged_at = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            review_times.append((merged_at - created).days)

        avg_review_days = (
            round(sum(review_times) / len(review_times), 2) if review_times else 0
        )

        return {
            "total_prs_analyzed": len(prs),
            "merged_count": len(merged),
            "closed_without_merge": len(closed_not_merged),
            "merge_rate": round(len(merged) / len(prs) * 100, 2) if prs else 0,
            "avg_comments_per_pr": avg_comments,
            "avg_review_time_days": avg_review_days,
        }

    def check_community_health(self, owner: str, repo: str) -> Dict:
        """Check community health indicators."""
        # Check for important files
        readme = self._make_request(f"repos/{owner}/{repo}/readme")
        license_info = self._make_request(f"repos/{owner}/{repo}/license")
        contributing = self._make_request(
            f"repos/{owner}/{repo}/contents/CONTRIBUTING.md"
        )
        code_of_conduct = self._make_request(
            f"repos/{owner}/{repo}/contents/CODE_OF_CONDUCT.md"
        )

        # Get releases
        releases = self._make_request(f"repos/{owner}/{repo}/releases")

        return {
            "has_readme": readme is not None,
            "has_license": license_info is not None,
            "has_contributing": contributing is not None,
            "has_code_of_conduct": code_of_conduct is not None,
            "total_releases": len(releases) if releases else 0,
            "latest_release": (
                releases[0].get("tag_name") if releases and len(releases) > 0 else "N/A"
            ),
        }

    def check_ci_cd(self, owner: str, repo: str) -> Dict:
        """Check CI/CD configuration."""
        workflows = self._make_request(f"repos/{owner}/{repo}/actions/workflows")

        if not workflows or "workflows" not in workflows:
            return {"has_github_actions": False, "workflow_count": 0, "workflows": []}

        workflow_list = workflows["workflows"]
        return {
            "has_github_actions": len(workflow_list) > 0,
            "workflow_count": len(workflow_list),
            "workflows": [w.get("name") for w in workflow_list[:5]],
        }

    def calculate_health_score(self, repo_data: Dict) -> Dict:
        """Calculate overall health score based on various metrics."""
        score = 0
        max_score = 100
        details = []

        # Activity score (30 points)
        commits_per_month = repo_data.get("commit_analysis", {}).get(
            "commits_per_month", 0
        )
        if commits_per_month > 10:
            score += 30
            details.append("High activity: 30/30")
        elif commits_per_month > 5:
            score += 20
            details.append("Medium activity: 20/30")
        elif commits_per_month > 0:
            score += 10
            details.append("Low activity: 10/30")
        else:
            details.append("No recent activity: 0/30")

        # Community score (25 points)
        community = repo_data.get("community_health", {})
        community_score = 0
        if community.get("has_readme"):
            community_score += 5
        if community.get("has_license"):
            community_score += 5
        if community.get("has_contributing"):
            community_score += 5
        if community.get("has_code_of_conduct"):
            community_score += 5
        if community.get("total_releases", 0) > 0:
            community_score += 5
        score += community_score
        details.append(f"Community health: {community_score}/25")

        # Issue responsiveness (20 points)
        avg_close_days = repo_data.get("issue_analysis", {}).get(
            "average_close_time_days", 999
        )
        if avg_close_days < 7:
            score += 20
            details.append("Excellent issue response: 20/20")
        elif avg_close_days < 30:
            score += 15
            details.append("Good issue response: 15/20")
        elif avg_close_days < 90:
            score += 10
            details.append("Average issue response: 10/20")
        else:
            details.append("Slow issue response: 0/20")

        # PR quality (15 points)
        merge_rate = repo_data.get("pr_analysis", {}).get("merge_rate", 0)
        if merge_rate > 70:
            score += 15
            details.append("High PR merge rate: 15/15")
        elif merge_rate > 50:
            score += 10
            details.append("Medium PR merge rate: 10/15")
        elif merge_rate > 0:
            score += 5
            details.append("Low PR merge rate: 5/15")
        else:
            details.append("No PR data: 0/15")

        # CI/CD (10 points)
        if repo_data.get("ci_cd", {}).get("has_github_actions"):
            score += 10
            details.append("Has CI/CD: 10/10")
        else:
            details.append("No CI/CD: 0/10")

        # Normalize score to 0-100
        normalized_score = min(100, score)
        grade = self._get_grade(normalized_score)

        return {
            "overall_score": normalized_score,
            "max_score": max_score,
            "grade": grade,
            "score_breakdown": details,
        }

    def _get_grade(self, score: float) -> str:
        """Convert score to letter grade."""
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"

    def analyze_repository(self, repo_url: str) -> Dict:
        """
        Comprehensive repository analysis.

        Args:
            repo_url: GitHub repository URL or owner/repo format

        Returns:
            Complete analysis results dictionary
        """
        # Parse repo URL
        parts = repo_url.replace("https://github.com/", "").strip("/").split("/")
        if len(parts) < 2:
            return {"error": "Invalid repository URL format. Use: owner/repo or full URL"}

        owner, repo = parts[0], parts[1]

        logger.info(f"Analyzing repository: {owner}/{repo}")

        # Gather all data
        basic_info = self.get_repo_info(owner, repo)
        if not basic_info:
            return {"error": f"Repository {owner}/{repo} not found or inaccessible"}

        commit_analysis = self.analyze_commit_frequency(owner, repo)
        contributor_analysis = self.analyze_contributors(owner, repo)
        issue_analysis = self.analyze_issues(owner, repo)
        pr_analysis = self.analyze_pull_requests(owner, repo)
        community_health = self.check_community_health(owner, repo)
        ci_cd = self.check_ci_cd(owner, repo)

        # Combine all data
        repo_data = {
            "repository": f"{owner}/{repo}",
            "url": f"https://github.com/{owner}/{repo}",
            "analyzed_at": datetime.now().isoformat(),
            "basic_info": basic_info,
            "commit_analysis": commit_analysis,
            "contributor_analysis": contributor_analysis,
            "issue_analysis": issue_analysis,
            "pr_analysis": pr_analysis,
            "community_health": community_health,
            "ci_cd": ci_cd,
        }

        # Calculate health score
        repo_data["health_score"] = self.calculate_health_score(repo_data)

        return repo_data


@tool
@log_io
def github_analyzer_tool(
    repo_urls: Annotated[
        str,
        "Comma-separated list of GitHub repository URLs or owner/repo format (e.g., 'facebook/react,vuejs/vue')",
    ],
) -> str:
    """
    Analyze GitHub repositories for tech selection purposes.

    This tool performs comprehensive analysis including:
    - Basic info (stars, forks, language, license)
    - Commit frequency (last 3 months)
    - Issue response time and status
    - PR merge rate and discussion quality
    - Community health indicators
    - CI/CD setup
    - Overall health score

    Returns a detailed analysis report for comparison and selection.
    """
    try:
        analyzer = GitHubAnalyzer()

        # Parse multiple repositories
        repos = [r.strip() for r in repo_urls.split(",")]
        results = []

        for repo_url in repos:
            if not repo_url:
                continue

            result = analyzer.analyze_repository(repo_url)
            results.append(result)

        # Format results as a readable report
        if len(results) == 1:
            return _format_single_repo_report(results[0])
        else:
            return _format_comparison_report(results)

    except Exception as e:
        error_msg = f"GitHub analysis failed: {repr(e)}"
        logger.error(error_msg)
        return error_msg


def _format_single_repo_report(data: Dict) -> str:
    """Format single repository analysis report."""
    if "error" in data:
        return f"Error: {data['error']}"

    basic = data.get("basic_info", {})
    commits = data.get("commit_analysis", {})
    contributors = data.get("contributor_analysis", {})
    issues = data.get("issue_analysis", {})
    prs = data.get("pr_analysis", {})
    community = data.get("community_health", {})
    ci_cd = data.get("ci_cd", {})
    health = data.get("health_score", {})

    report = f"""# GitHub Repository Analysis: {data.get('repository')}

## Overall Health Score: {health.get('overall_score', 0)}/100 (Grade: {health.get('grade', 'N/A')})

### Basic Information
- **Description**: {basic.get('description', 'N/A')}
- **Language**: {basic.get('language', 'N/A')}
- **License**: {basic.get('license', 'N/A')}
- **Stars**: {basic.get('stars', 0):,}
- **Forks**: {basic.get('forks', 0):,}
- **Watchers**: {basic.get('watchers', 0):,}
- **Open Issues**: {basic.get('open_issues', 0)}
- **Repository Size**: {basic.get('size', 0)} KB
- **Created**: {basic.get('created_at', 'N/A')[:10]}
- **Last Updated**: {basic.get('updated_at', 'N/A')[:10]}
- **Archived**: {'Yes' if basic.get('archived') else 'No'}

### Activity Metrics (Last 3 Months)
- **Total Commits**: {commits.get('total_commits', 0)}
- **Commits per Month**: {commits.get('commits_per_month', 0)}
- **Commits per Week**: {commits.get('commits_per_week', 0)}

### Contributors
- **Total Contributors**: {contributors.get('total_contributors', 0)}
- **Top Contributors**: {', '.join([c['username'] for c in contributors.get('top_contributors', [])])}

### Issue Management
- **Open Issues**: {issues.get('open_issues_count', 0)}
- **Closed Issues Analyzed**: {issues.get('closed_issues_analyzed', 0)}
- **Average Close Time**: {issues.get('average_close_time_days', 0)} days
- **Open/Close Ratio**: {issues.get('open_close_ratio', 0)}

### Pull Request Quality
- **Total PRs Analyzed**: {prs.get('total_prs_analyzed', 0)}
- **Merged PRs**: {prs.get('merged_count', 0)}
- **Merge Rate**: {prs.get('merge_rate', 0)}%
- **Average Comments per PR**: {prs.get('avg_comments_per_pr', 0)}
- **Average Review Time**: {prs.get('avg_review_time_days', 0)} days

### Community Health
- **README**: {'✅' if community.get('has_readme') else '❌'}
- **License**: {'✅' if community.get('has_license') else '❌'}
- **Contributing Guide**: {'✅' if community.get('has_contributing') else '❌'}
- **Code of Conduct**: {'✅' if community.get('has_code_of_conduct') else '❌'}
- **Total Releases**: {community.get('total_releases', 0)}
- **Latest Release**: {community.get('latest_release', 'N/A')}

### CI/CD
- **GitHub Actions**: {'✅ Enabled' if ci_cd.get('has_github_actions') else '❌ Not configured'}
- **Workflow Count**: {ci_cd.get('workflow_count', 0)}
- **Workflows**: {', '.join(ci_cd.get('workflows', [])) if ci_cd.get('workflows') else 'N/A'}

### Score Breakdown
{chr(10).join(f'- {detail}' for detail in health.get('score_breakdown', []))}

---
*Analysis URL*: {data.get('url')}
*Analyzed at*: {data.get('analyzed_at', 'N/A')[:19]}
"""
    return report


def _format_comparison_report(results: List[Dict]) -> str:
    """Format multiple repositories comparison report."""
    valid_results = [r for r in results if "error" not in r]

    if not valid_results:
        return "Error: No valid repositories could be analyzed."

    report = "# GitHub Repositories Comparison\n\n"

    # Comparison table
    report += "## Overview Comparison\n\n"
    report += "| Repository | Stars | Language | Health Score | Commits/Month | Avg Issue Close (days) | PR Merge Rate |\n"
    report += "|------------|-------|----------|--------------|---------------|------------------------|---------------|\n"

    for data in valid_results:
        basic = data.get("basic_info", {})
        commits = data.get("commit_analysis", {})
        issues = data.get("issue_analysis", {})
        prs = data.get("pr_analysis", {})
        health = data.get("health_score", {})

        report += (
            f"| {data.get('repository', 'N/A')} "
            f"| {basic.get('stars', 0):,} "
            f"| {basic.get('language', 'N/A')} "
            f"| {health.get('overall_score', 0)} ({health.get('grade', 'N/A')}) "
            f"| {commits.get('commits_per_month', 0)} "
            f"| {issues.get('average_close_time_days', 0)} "
            f"| {prs.get('merge_rate', 0)}% |\n"
        )

    # Detailed analysis for each repo
    report += "\n## Detailed Analysis\n\n"
    for i, data in enumerate(valid_results, 1):
        report += f"### {i}. {data.get('repository', 'N/A')}\n\n"
        report += _format_single_repo_report(data)
        report += "\n---\n\n"

    return report
